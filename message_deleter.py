# message_deleter_fixed.py - VERSÃO FINAL CORRIGIDA (Correções de estabilidade, race, deadlocks, leaks)
import os
import time
import json
import random
import re
import asyncio
import math
import traceback
from datetime import datetime, timedelta, timezone
from typing import Optional, Callable, List, Dict, Any
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.edge.service import Service as EdgeService
from selenium.webdriver.firefox.service import Service as FirefoxService
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.firefox.options import Options as FirefoxOptions
import httpx
import shutil
import tempfile
import sys
import gc
import signal
from contextlib import contextmanager
import threading
from collections import deque

# ----------------------------
# CONFIGURÁVEIS OTIMIZADAS - ANTI RATE LIMIT
# ----------------------------
API_BASE = "https://discord.com/api/v9"
MAX_CONCURRENT_REQUESTS = 1  # SERIAL - evita 429 em cascata
REQUEST_MIN_DELAY = 1.5  # AUMENTADO para evitar rate limits
DEFAULT_FETCH_PAGE_LIMIT = 100
SUPER_LOTE_SIZE = 400  # REDUZIDO para menos memória
CHUNK_SIZE = 50  # Chunks menores para liberar memória
MAX_PAGES_PER_LOTE = 500  # Proteção contra loop infinito
CLIENT_RECREATE_INTERVAL = 5  # Recria cliente a cada 5 canais
FORCE_GC_INTERVAL = 50  # GC forçado a cada 50 deleções
SEEN_BEFORES_MAXLEN = 2048  # tamanho do histórico de cursors (deque)

# Rate Limit Protection
CONSECUTIVE_429_COOLDOWN_THRESHOLD = 3  # Após 3 429s seguidos, pausa longa
COOLDOWN_AFTER_429_BURST = 30  # 30 segundos de cooldown

# Timeouts
HTTP_REQUEST_TIMEOUT = 30.0  # segundos para cada request HTTP
CLIENT_CLOSE_TIMEOUT = 10.0

# ----------------------------
# Classe principal
# ----------------------------
class DiscordMessageDeleter:
    def __init__(self, max_concurrent_requests: int = MAX_CONCURRENT_REQUESTS, fetch_all_by_default: bool = True):
        self.driver = None
        self.token = None
        self.async_client: Optional[httpx.AsyncClient] = None
        self.headers = None
        self.user_id = None
        self.user_info = None
        self.stats = {
            'start_time': None,
            'deleted_count': 0,
            'failed_count': 0,
            'throttled_count': 0,
            'throttled_total_time': 0.0,
            'last_ping': 0.0,
            'avg_ping': 0.0,
            'client_recreate_count': 0,
            'gc_forced_count': 0
        }
        self.max_concurrent_requests = max_concurrent_requests
        # semáforo para controlar concorrência das requisições HTTP
        # Fix Crítico: asyncio.Semaphore must be used inside the loop. Initialized lazily.
        self._semaphore = None
        self.fetch_all_by_default = fetch_all_by_default

        # safety: optional hard cap to avoid accidental full wipes; None = disabled
        self.max_total_deletes: Optional[int] = None

        # thread-safe stop event (usado por signal handler)
        self._stop_event = threading.Event()
        
        # Lock para proteger inicialização do semáforo (thread-safe)
        self._semaphore_lock = threading.Lock()

        # cria um event loop em thread separada (graceful, para permitir run_coroutine_threadsafe)
        self.loop = asyncio.new_event_loop()
        self._loop_thread = threading.Thread(target=self._start_loop, daemon=True)
        self._loop_thread.start()

        # normaliza configs
        self._normalize_config()

    def _start_loop(self):
        """Executa o loop em thread separada."""
        try:
            asyncio.set_event_loop(self.loop)
            self.loop.run_forever()
        except Exception as e:
            print(f"⚠️ Erro na thread do loop: {e}")
        finally:
            try:
                self.loop.close()
            except Exception:
                pass

    def _normalize_config(self):
        """Normaliza e valida configurações que podem ser ambíguas."""
        if self.max_total_deletes is not None:
            try:
                self.max_total_deletes = int(self.max_total_deletes)
                if self.max_total_deletes <= 0:
                    # Interpretar 0/negativo como desabilitado para evitar parada imediata por erro de configuração
                    print("⚠️ max_total_deletes inválido (<=0). Interpretando como desabilitado (None).")
                    self.max_total_deletes = None
            except Exception:
                print("⚠️ max_total_deletes não é inteiro. Interpretando como desabilitado (None).")
                self.max_total_deletes = None

    # Utilitário para executar corrotinas de forma síncrona usando run_coroutine_threadsafe
    def run_async(self, coro, timeout: Optional[float] = None):
        """
        Agrega uma corrotina ao loop em thread e aguarda resultado.
        Usa run_coroutine_threadsafe para compatibilidade com o loop rodando.
        """
        if not self.loop or not self._loop_thread.is_alive():
            raise RuntimeError("Event loop não está rodando.")
        
        # CORREÇÃO: Verifica stop_event antes de iniciar
        if self._stop_event.is_set():
            raise asyncio.CancelledError("Operação já foi cancelada.")
            
        future = asyncio.run_coroutine_threadsafe(coro, self.loop)
        try:
            return future.result(timeout=timeout)
        except TimeoutError:
            print(f"⚠️ Timeout em run_async ({timeout}s). Cancelando tarefa em background...")
            future.cancel()
            raise
        except Exception as e:
            # CORREÇÃO: Não propaga exceção se foi cancelamento
            if self._stop_event.is_set():
                raise asyncio.CancelledError("Operação cancelada pelo usuário.")
            raise

    # ----------------------------
    # Obter token via webpack do Discord (headless)
    # ----------------------------
    def get_discord_token_safe(self):
        """Método seguro para obter token via webpack"""
        try:
            js_code = """
            let token = null;
            window.webpackChunkdiscord_app.push([
                [Symbol()],
                {},
                req => {
                    if (!req.c) return;
                    for (let m of Object.values(req.c)) {
                        try {
                            if (!m.exports || m.exports === window) continue;
                            if (m.exports?.getToken) {
                                token = m.exports.getToken();
                                break;
                            }
                            for (let ex in m.exports) {
                                if (m.exports?.[ex]?.getToken && m.exports[ex][Symbol.toStringTag] !== 'IntlMessagesProxy') {
                                    token = m.exports[ex].getToken();
                                    break;
                                }
                            }
                        } catch {}
                    }
                },
            ]);
            window.webpackChunkdiscord_app.pop();
            return token;
            """
            token = self.driver.execute_script(js_code)
            if token and len(token) > 50:
                print("✅ Token obtido com sucesso")
                return token
            return None
        except Exception as e:
            print(f"❌ Erro ao obter token: {e}")
            return None

    # ----------------------------
    # Setup Selenium
    # ----------------------------
    def setup_selenium(self, headless: bool = True):
        """Configura o Selenium WebDriver com fallback (Chrome -> Brave -> Edge -> Firefox)"""
        
        def _configure_common_options(options):
            if headless:
                options.add_argument("--headless=new")
            options.add_argument("--window-size=1920,1080")
            options.add_argument("--disable-blink-features=AutomationControlled")
            options.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
            options.add_experimental_option("useAutomationExtension", False)
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
            return options

        # 1. Tentar Chrome / Brave
        try:
            print("🚀 Tentando inicializar Chrome/Brave...")
            chrome_paths = [
                'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
                'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe',
                os.path.expanduser('~\\AppData\\Local\\Google\\Chrome\\Application\\chrome.exe'),
                'C:\\Program Files\\BraveSoftware\\Brave-Browser\\Application\\brave.exe', # Brave
                os.path.expanduser('~\\AppData\\Local\\BraveSoftware\\Brave-Browser\\Application\\brave.exe') # Brave User
            ]
            
            binary_location = None
            for path in chrome_paths:
                if os.path.exists(path):
                    binary_location = path
                    print(f"   Encontrado binário: {path}")
                    break
            
            options = Options()
            if binary_location:
                options.binary_location = binary_location
            
            _configure_common_options(options)
            
            # Use a persistent temp dir for 2FA flows to potentially save some state if needed, 
            # though we clear it after, it helps during the session.
            self.temp_user_data_dir = tempfile.mkdtemp(prefix="chrome_data_") 
            options.add_argument(f"--user-data-dir={self.temp_user_data_dir}")

            self.driver = webdriver.Chrome(options=options)
            self._apply_stealth()
            print("✅ Chrome/Brave inicializado com sucesso!")
            return self.driver
        except Exception as e:
            print(f"⚠️ Falha ao iniciar Chrome/Brave: {e}")

        # 2. Tentar Edge
        try:
            print("🚀 Tentando inicializar Edge...")
            options = EdgeOptions()
            # Edge options need to be configured similarly
            if headless:
                options.add_argument("--headless=new")
            options.add_argument("--window-size=1920,1080")
            options.add_argument("--disable-blink-features=AutomationControlled")
            options.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
            options.add_experimental_option("useAutomationExtension", False)
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            
            self.driver = webdriver.Edge(options=options)
            self._apply_stealth()
            print("✅ Edge inicializado com sucesso!")
            return self.driver
        except Exception as e:
            print(f"⚠️ Falha ao iniciar Edge: {e}")

        # 3. Tentar Firefox
        try:
            print("🚀 Tentando inicializar Firefox...")
            options = FirefoxOptions()
            if headless:
                options.add_argument("--headless")
            options.add_argument("--width=1920")
            options.add_argument("--height=1080")
            
            self.driver = webdriver.Firefox(options=options)
            print("✅ Firefox inicializado com sucesso!")
            return self.driver
        except Exception as e:
            print(f"⚠️ Falha ao iniciar Firefox: {e}")

        print("❌ ERRO FATAL: Nenhum navegador suportado (Chrome, Brave, Edge, Firefox) pôde ser iniciado.")
        return None

    def _apply_stealth(self):
        """Aplica patches anti-detecção no driver atual"""
        try:
            if not self.driver: return
            self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            try:
                self.driver.execute_cdp_cmd('Network.setUserAgentOverride', {
                    "userAgent": 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                })
            except: pass
        except: pass

    # ----------------------------
    # Login helpers
    # ----------------------------
    def wait_for_login_success(self, timeout=90, expect_2fa=False):
        """Aguarda o login ser bem-sucedido com múltiplas estratégias"""
        print("⏳ Aguardando confirmação de login...")
        start_time = time.time()
        while time.time() - start_time < timeout:
            if self._stop_event.is_set():
                print("⏹️ Stop event set — interrompendo wait_for_login_success")
                return False
            try:
                current_url = self.driver.current_url
                if any(pattern in current_url for pattern in ['channels', 'app', 'library']):
                    print("✅ Login confirmado pela URL")
                    return True

                login_indicators = [
                    "//div[contains(@class, 'privateChannels')]",
                    "//div[contains(@class, 'guilds')]",
                    "//div[contains(@class, 'chatContent')]",
                    "//div[contains(text(), 'Friends')]",
                    "//div[contains(text(), 'Amigos')]",
                    "//button[contains(@aria-label, 'User Settings')]",
                ]
                for indicator in login_indicators:
                    try:
                        elements = self.driver.find_elements(By.XPATH, indicator)
                        if elements:
                            print(f"✅ Login confirmado pelo elemento: {indicator}")
                            return True
                    except:
                        continue

                # Se estamos esperando 2FA, não falhamos por detectar campos de 2FA
                # apenas continuamos esperando o usuário completar
                if not expect_2fa:
                    error_indicators = [
                        "//div[contains(text(), 'Invalid login') ]",
                        "//div[contains(text(), 'Wrong email') ]",
                        "//div[contains(text(), 'Wrong password') ]",
                        "//div[contains(text(), 'Login inválido') ]",
                    ]
                    for error_indicator in error_indicators:
                        try:
                            elements = self.driver.find_elements(By.XPATH, error_indicator)
                            if elements:
                                print("❌ Credenciais inválidas detectadas")
                                return False
                        except:
                            continue

                    try:
                        code_input = self.driver.find_elements(By.NAME, "code")
                        if code_input:
                            print("🔐 2FA detectado")
                            return "2FA_REQUIRED"
                    except:
                        pass

                    try:
                        captcha_iframe = self.driver.find_elements(By.XPATH, "//iframe[contains(@title, 'hCaptcha')]")
                        if captcha_iframe:
                            print("❌ CAPTCHA detectado. O login headless não pode continuar.")
                            print("❌ Tente novamente mais tarde ou com uma conexão de internet diferente.")
                            return False
                    except:
                        pass

                time.sleep(2)
            except Exception as e:
                print(f"⚠️ Erro durante verificação de login: {e}")
                time.sleep(2)
        print("❌ Timeout na verificação de login")
        return False

    def login(self, email, password, has_2fa=False):
        """Login melhorado com opção de 2FA manual (non-headless)"""
        print(f"🔄 Iniciando processo de login no Discord (modo {'Visual' if has_2fa else 'Headless'})...")
        
        # Se tem 2FA, abre sem headless
        if not self.setup_selenium(headless=not has_2fa):
            print("❌ Falha ao configurar navegador")
            return False

        try:
            self.driver.get('https://discord.com/login')
            time.sleep(5)

            # Tenta preencher email e senha mesmo com 2FA, para agilizar
            print("📧 Preenchendo email...")
            try:
                email_input = WebDriverWait(self.driver, 20).until(
                    EC.presence_of_element_located((By.NAME, "email"))
                )
                email_input.clear()
                email_input.send_keys(email)
                print("✅ Email preenchido")
            except TimeoutException:
                print("⚠️ Campo de email não encontrado (talvez já logado?)")

            print("🔒 Preenchendo senha...")
            try:
                password_input = self.driver.find_element(By.NAME, "password")
                password_input.clear()
                password_input.send_keys(password)
                print("✅ Senha preenchida")
            except NoSuchElementException:
                print("⚠️ Campo de senha não encontrado")

            print("🚀 Clicando em login...")
            try:
                submit_button = self.driver.find_element(By.XPATH, "//button[@type='submit']")
                submit_button.click()
                print("✅ Botão de login clicado")
            except NoSuchElementException:
                print("⚠️ Botão de login não encontrado")

            # Se tem 2FA, damos muuuito mais tempo e não falhamos se detectar 2FA
            timeout = 300 if has_2fa else 60 # 5 minutos para 2FA manual
            login_result = self.wait_for_login_success(timeout, expect_2fa=has_2fa)

            if login_result == "2FA_REQUIRED" and not has_2fa:
                print("❌ 2FA detectado em modo headless. Use a opção 'Tem 2FA' na tela de login.")
                return False

            if login_result is True:
                print("✅ Login bem-sucedido! Obtendo token...")
                time.sleep(5)

                max_attempts = 10
                for attempt in range(max_attempts):
                    print(f"🔄 Tentativa {attempt + 1}/{max_attempts} de obter token...")
                    self.token = self.get_discord_token_safe()
                    if self.token:
                        print("✅ Token obtido com sucesso")
                        break
                    if self._stop_event.is_set():
                        return False
                    time.sleep(3)

                if not self.token:
                    print("❌ Não foi possível obter o token")
                    return False

                self.setup_api_session()
                self.user_info = self.get_user_info_sync()

                if self.user_info:
                    self.user_id = self.user_info['id']
                    print(f"👤 Usuário autenticado: {self.user_info.get('global_name', self.user_info.get('username', 'N/A'))}")

                    delay = random.uniform(3, 6)
                    print(f"⏳ Estabilizando token... aguardando {delay:.1f} segundos.")
                    time.sleep(delay)
                    print("✅ Token estável. A sessão da API está pronta.")
                    return True
                else:
                    print("❌ Token inválido ou expirado")
                    return False
            else:
                print("❌ Falha no login - credenciais inválidas ou timeout")
                return False
        except Exception as e:
            print(f"❌ Erro durante o login: {e}")
            traceback.print_exc()
            return False
        finally:
            if self.driver:
                print("🧹 Limpando e fechando o navegador...")
                try:
                    self.driver.quit()
                except Exception as e:
                    print(f"⚠️ Erro ao fechar o driver: {e}")
                self.driver = None
            
            # Limpa diretório temporário do Chrome
            if hasattr(self, 'temp_user_data_dir') and self.temp_user_data_dir:
                try:
                    if os.path.exists(self.temp_user_data_dir):
                        shutil.rmtree(self.temp_user_data_dir, ignore_errors=True)
                        print(f"🧹 Pasta temporária do login removida: {self.temp_user_data_dir}")
                except Exception as e:
                    print(f"⚠️ Erro ao remover temp dir no login: {e}")
                finally:
                    self.temp_user_data_dir = None

    # ----------------------------
    # Setup API
    # ----------------------------
    def _close_async_client(self, timeout: float = CLIENT_CLOSE_TIMEOUT):
        """Fecha o client atual de forma segura, suportando loop em thread."""
        if not self.async_client:
            return
        async def _close():
            try:
                await self.async_client.aclose()
            except Exception as e:
                print(f"⚠️ Erro no aclose do client: {e}")
        try:
            fut = asyncio.run_coroutine_threadsafe(_close(), self.loop)
            fut.result(timeout=timeout)
        except Exception as e:
            print(f"⚠️ Falha ao fechar async client com timeout ({timeout}s): {e}")
        finally:
            # garante que referência seja removida
            self.async_client = None
            gc.collect()

    def setup_api_session(self):
        """Configura httpx.AsyncClient com headers apropriados e limites de conexão"""
        if not self.token:
            raise Exception("Token não configurado")

        # Fecha cliente anterior de forma robusta
        self._close_async_client()

        self.headers = {
            'authorization': self.token,
            'content-type': 'application/json',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'x-discord-timezone': 'America/Sao_Paulo',
        }

        # Limites de conexão para evitar acúmulo
        limits = httpx.Limits(
            max_keepalive_connections=5,
            max_connections=10,
            keepalive_expiry=30.0
        )

        self.async_client = httpx.AsyncClient(
            headers=self.headers,
            timeout=HTTP_REQUEST_TIMEOUT,
            limits=limits,
            http2=False  # HTTP/1.1 mais estável com Discord
        )

        self.stats['client_recreate_count'] += 1
        print(f"🔄 AsyncClient recriado (#{self.stats['client_recreate_count']})")

    def before_request(self):
        self.stats['_before_ts'] = time.time() * 1000

    def after_request(self):
        if hasattr(self, 'stats') and '_before_ts' in self.stats:
            ping = (time.time() * 1000) - self.stats['_before_ts']
            self.stats['last_ping'] = ping
            self.stats['avg_ping'] = self.stats['avg_ping'] * 0.9 + ping * 0.1 if self.stats['avg_ping'] > 0 else ping

    async def async_api_request(self, method: str, url: str, params: Optional[Dict] = None, json_data: Optional[Dict] = None, max_retries: int = 6):
        """Realiza uma requisição HTTP assíncrona com semáforo, retry e tratamento robusto de 429"""
        if not self.async_client:
            # se não houver client, crie (seguro pois setup_api_session usa run_coroutine_threadsafe)
            self.setup_api_session()

        attempt = 0
        backoff_base = 1.5  # Aumentado para backoff mais agressivo

        while attempt < max_retries:
            if self._stop_event.is_set():
                raise asyncio.CancelledError("Operação abortada pelo usuário.")
            attempt += 1
            # Delay mínimo aumentado antes de cada tentativa
            await asyncio.sleep(REQUEST_MIN_DELAY)

            try:
                # Acquire do semáforo apenas para a chamada de rede.
                # CORREÇÃO: Inicialização thread-safe do semáforo
                if self._semaphore is None:
                    with self._semaphore_lock:
                        if self._semaphore is None:  # Double-check locking
                            self._semaphore = asyncio.Semaphore(self.max_concurrent_requests)

                async with self._semaphore:
                    self.before_request()
                    
                    # O request continua sendo async/await pois é do httpx
                    resp = await asyncio.wait_for(
                        self.async_client.request(method, url, params=params, json=json_data),
                        timeout=HTTP_REQUEST_TIMEOUT
                    )
                    
                    self.after_request()

                # Tratar códigos de sucesso
                if resp.status_code in (200, 201, 204):
                    return {} if resp.status_code == 204 else resp.json()

                # 401 - Token Inválido (CRÍTICO)
                if resp.status_code == 401:
                    print("\n🚨 ERRO CRÍTICO: Token inválido ou expirado (401).")
                    print("⏹️ Parando execução imediatamente para segurança da conta.")
                    self._stop_event.set()
                    raise Exception("Token inválido (401) - Verifique se a senha foi alterada.")

                # Tratamento dedicado para 429 (rate limit)
                if resp.status_code == 429:
                    self.stats['throttled_count'] += 1
                    retry_after = 2.0  # Padrão mais alto
                    is_global = False
                    try:
                        body = resp.json()
                        retry_after = float(body.get('retry_after', retry_after))
                        is_global = bool(body.get('global', False))
                    except Exception:
                        try:
                            retry_after = float(resp.headers.get('retry-after', retry_after) or retry_after)
                        except Exception:
                            retry_after = retry_after
                        is_global = resp.headers.get('x-ratelimit-global', 'false').lower() == 'true'

                    self.stats['throttled_total_time'] += retry_after

                    # Espera exponencial aumentada
                    wait = retry_after * 1.5 + (backoff_base * (2 ** (attempt - 1)))
                    if is_global:
                        wait *= 2  # Global = espera dobrada
                        print(f"🚨 GLOBAL RATE LIMIT! Esperando {wait:.1f}s (tentativa {attempt}/{max_retries})")
                    else:
                        print(f"⚠️ Rate limit (429). Esperando {wait:.1f}s (tentativa {attempt}/{max_retries})")

                    # Antes de dormir, permita que outros tasks rodem
                    await asyncio.sleep(wait)
                    continue

                # Outros erros
                if resp.status_code == 404:
                    return None  # Já deletada
                if resp.status_code == 403:
                    print(f"❌ Sem permissão (403) para {method} {url}")
                    return None

                text = resp.text[:200]
                raise Exception(f"HTTP {resp.status_code}: {text}")

            except asyncio.TimeoutError:
                wait = backoff_base * (2 ** (attempt - 1))
                print(f"⚠️ Timeout na requisição (tentativa {attempt}/{max_retries}). Esperando {wait:.1f}s")
                await asyncio.sleep(wait)
                # recria client em erros persistentes para limpar sockets
                if attempt >= 3:
                    print("🔧 Recriando cliente após timeout persistente...")
                    try:
                        self.setup_api_session()
                    except Exception as e:
                        print(f"⚠️ Erro ao recriar client: {e}")
                continue

            except httpx.RequestError as e:
                wait = backoff_base * (2 ** (attempt - 1))
                print(f"⚠️ Erro de conexão httpx (tentativa {attempt}/{max_retries}): {e}. Esperando {wait:.1f}s")
                await asyncio.sleep(wait)
                if attempt >= 3:
                    print("🔧 Recriando cliente após erro persistente...")
                    try:
                        self.setup_api_session()
                    except Exception as e:
                        print(f"⚠️ Erro ao recriar client: {e}")
                continue

            except asyncio.CancelledError:
                print("⏹️ Requisição cancelada via stop_event.")
                raise

            except Exception as e:
                if attempt >= max_retries:
                    raise
                wait = backoff_base * (2 ** (attempt - 1))
                print(f"⚠️ Erro na requisição (tentativa {attempt}/{max_retries}): {e}. Retentando em {wait:.1f}s.")
                await asyncio.sleep(wait)
                # se muitos erros, tenta recriar client
                if attempt >= 3:
                    try:
                        self.setup_api_session()
                    except Exception as e2:
                        print(f"⚠️ Erro ao recriar client (2): {e2}")
                continue

        raise Exception("Máximo de retries atingido para requisição API.")

    # ----------------------------
    # Wrappers síncronos — usam run_async (que usa run_coroutine_threadsafe)
    # ----------------------------
    def safe_api_get(self, url, params=None, delay=0.0):
        """Wrapper síncrono para GET assíncrono"""
        return self.run_async(self.async_api_request('GET', url, params=params))

    def get_user_info_sync(self):
        """Obtém info do usuário (síncrono wrapper)"""
        try:
            return self.run_async(self.async_api_request('GET', f'{API_BASE}/users/@me'))
        except Exception as e:
            print(f"❌ Exceção ao obter info usuário: {e}")
            return None

    def get_user_info(self):
        """Alias para compatibilidade"""
        return self.user_info

    def get_dms(self):
        """Lista DMs (síncrono wrapper)"""
        try:
            dms = self.run_async(self.async_get_dms())
            formatted_dms = []
            for dm in dms:
                recipients = [r for r in dm.get('recipients', []) if r.get('id') != self.user_id]
                dm_info = {
                    'id': dm['id'],
                    'name': 'DM',
                    'username': '',
                    'avatar': None,
                    'type': 'dm' if dm.get('type') == 1 else 'group',
                    'last_message_id': dm.get('last_message_id', '0')
                }
                if recipients:
                    recipient = recipients[0]
                    dm_info['user_id'] = recipient.get('id')
                    dm_info['name'] = recipient.get('global_name', recipient.get('username', 'Unknown User'))
                    dm_info['username'] = recipient.get('username', 'unknown')
                    dm_info['avatar'] = recipient.get('avatar')
                formatted_dms.append(dm_info)

            formatted_dms.sort(key=lambda x: int(x['last_message_id'] or 0), reverse=True)
            seen = set()
            unique_dms = []
            for dm_info in formatted_dms:
                uid = dm_info.get('user_id', dm_info['id'])
                if uid not in seen:
                    seen.add(uid)
                    unique_dms.append(dm_info)
            return unique_dms
        except Exception as e:
            print(f"❌ Exceção ao obter DMs: {e}")
            return []

    def get_servers(self):
        """Lista servidores (síncrono wrapper)"""
        try:
            servers = self.run_async(self.async_api_request('GET', f'{API_BASE}/users/@me/guilds'))
            return servers or []
        except Exception as e:
            print(f"❌ Exceção ao obter servidores: {e}")
            return []

    def get_server_channels(self, server_id):
        """Canais do servidor (síncrono wrapper)"""
        try:
            channels = self.run_async(self.async_api_request('GET', f'{API_BASE}/guilds/{server_id}/channels'))
            text_channels = [ch for ch in channels if ch.get('type') in [0, 5]]
            return text_channels
        except Exception as e:
            print(f"❌ Exceção ao obter canais do servidor {server_id}: {e}")
            return []

    # ----------------------------
    # Async message fetching & pagination
    # ----------------------------
    async def async_fetch_messages_page(self, channel_id: str, limit: int = DEFAULT_FETCH_PAGE_LIMIT, before: Optional[str] = None):
        """Busca UMA página de mensagens do canal"""
        params = {'limit': min(limit, DEFAULT_FETCH_PAGE_LIMIT)}
        if before:
            params['before'] = before
        url = f'{API_BASE}/channels/{channel_id}/messages'
        data = await self.async_api_request('GET', url, params=params)
        return data or []

    async def async_fetch_all_messages(self, channel_id: str, on_progress: Optional[Callable] = None):
        """
        Faz paginação completa para buscar todas as mensagens (OTIMIZADO PARA VELOCIDADE).
        """
        all_messages = []
        before = None
        page = 0
        seen_befores = deque(maxlen=SEEN_BEFORES_MAXLEN)
        consecutive_empty = 0

        while True:
            if self._stop_event.is_set():
                break
            
            page += 1
            # LIMIT=100 é mandatório para velocidade máxima
            page_msgs = await self.async_fetch_messages_page(channel_id, limit=100, before=before)
            
            if not page_msgs:
                consecutive_empty += 1
                if consecutive_empty >= 3:
                    break
                await asyncio.sleep(0.5) # Espera um pouco se falhar
                continue

            consecutive_empty = 0
            last_id = page_msgs[-1]['id']
            
            # Proteção contra loop infinito
            if last_id in seen_befores:
                break
            seen_befores.append(last_id)

            all_messages.extend(page_msgs)
            before = last_id
            
            # --- CALLBACK DE PROGRESSO PARA A UI ---
            if on_progress:
                try:
                    # Envia apenas o total acumulado para a UI mostrar "Preparando: 500..."
                    # Note: fetch é rápido, pode disparar muitas atualizações, o Streamlit aguenta
                    on_progress(len(all_messages), f"Página {page}")
                except Exception:
                    pass

            # GC forçado periodicamente (mantido para segurança de memória)
            if len(all_messages) % 2000 == 0:
                gc.collect()

            # --- OTIMIZAÇÃO DE VELOCIDADE AQUI ---
            # Antes estava random(0.4, 0.8). 
            # Para fetch, 0.1s é seguro o suficiente (10 req/s = 1000 msgs/s)
            await asyncio.sleep(0.1) 
            
            if len(page_msgs) < 100: # Se vier menos de 100, acabou o canal
                break

        # Limpeza final mais agressiva
        try:
            del page_msgs
        except NameError:
            pass
        gc.collect()
        return all_messages
    async def async_get_all_user_messages(self, channel: Dict, limit: int = 100, fetch_all: Optional[bool] = None, progress_callback: Optional[Callable] = None): # MODIFICADO
        """Retorna todas mensagens do usuário no canal com suporte a progresso"""
        if fetch_all is None:
            fetch_all = self.fetch_all_by_default
            
        channel_id = channel['id']
        channel_name = channel.get('name', 'DM') # Adicionado para o callback
        
        if fetch_all:
            # Modificação: O callback agora filtra e conta mensagens do usuário em tempo real
            all_messages = []
            user_messages = []
            
            async def _fetch_and_filter_progress(page_msgs):
                nonlocal all_messages, user_messages
                all_messages.extend(page_msgs)
                
                # Filtra apenas as novas mensagens da página
                new_user_msgs = [msg for msg in page_msgs if msg.get('author', {}).get('id') == self.user_id and not msg.get('pinned', False) and msg.get('type') in [0, 19]]
                user_messages.extend(new_user_msgs)
                
                if progress_callback:
                    try:
                        # Envia a contagem de mensagens do usuário e o nome do canal
                        progress_callback(len(user_messages), channel_name)
                    except Exception:
                        pass

            await self.async_fetch_all_messages_v2(channel_id, on_page_fetched=_fetch_and_filter_progress)
            return user_messages
        else:
            msgs = await self.async_fetch_messages_page(channel_id, limit=limit)    
            user_messages = [msg for msg in msgs if msg.get('author', {}).get('id') == self.user_id and not msg.get('pinned', False) and msg.get('type') in [0, 19]]
            return user_messages[:limit]

    async def async_fetch_all_messages_v2(self, channel_id: str, on_page_fetched: Optional[Callable] = None):
        """
        Versão otimizada do fetch que chama um callback com cada página de mensagens recebida.
        """
        before = None
        page = 0
        seen_befores = deque(maxlen=SEEN_BEFORES_MAXLEN)
        consecutive_empty = 0

        while True:
            if self._stop_event.is_set():
                break
            
            page += 1
            page_msgs = await self.async_fetch_messages_page(channel_id, limit=100, before=before)
            
            if not page_msgs:
                consecutive_empty += 1
                if consecutive_empty >= 3:
                    break
                await asyncio.sleep(0.5)
                continue

            consecutive_empty = 0
            last_id = page_msgs[-1]['id']
            
            if last_id in seen_befores:
                break
            seen_befores.append(last_id)

            if on_page_fetched:
                try:
                    await on_page_fetched(page_msgs)
                except Exception:
                    pass

            before = last_id
            
            if page % 20 == 0: # GC a cada 20 páginas
                gc.collect()

            await asyncio.sleep(0.1) 
            
            if len(page_msgs) < 100:
                break

        gc.collect()

    def get_all_user_messages(self, channel, limit=100, fetch_all=True, progress_callback=None): 
            return self.run_async(
                self.async_get_all_user_messages(
                    channel, 
                    limit=limit, 
                    fetch_all=fetch_all, 
                    progress_callback=progress_callback
                )
            )

    def get_user_messages(self, channel, limit=100, progress_callback=None):
        """Alias para compatibilidade"""
        return self.get_all_user_messages(channel, limit=limit, fetch_all=False, progress_callback=progress_callback)

    def get_messages_since_date(self, channel, since_date, progress_callback=None):
        """Obtém mensagens desde uma data específica (SÍNCRONO) - OTIMIZADO"""
        channel_name = channel.get('name', 'DM')
        
        # Wrapper síncrono para a versão async otimizada
        async def _async_get_since():
            filtered = []
            channel_id = channel['id']
            before = None
            
            while True:
                if self._stop_event.is_set(): break
                
                # Busca página de 100
                msgs = await self.async_fetch_messages_page(channel_id, limit=100, before=before)
                if not msgs: break
                
                page_filtered = []
                reached_limit = False
                
                for msg in msgs:
                    try:
                        msg_timestamp = datetime.fromisoformat(msg['timestamp'].replace('Z', '+00:00'))
                        if msg_timestamp >= since_date:
                            # Pertence ao usuário?
                            if msg.get('author', {}).get('id') == self.user_id:
                                page_filtered.append(msg)
                        else:
                            # Encontramos mensagem mais antiga que a data limite
                            # Como a API retorna em ordem decrescente, podemos parar aqui
                            reached_limit = True
                    except:
                        continue
                
                filtered.extend(page_filtered)
                
                # Progress callback
                if progress_callback:
                    try:
                        progress_callback(len(filtered), channel_name)
                    except Exception:
                        pass
                
                if reached_limit or len(msgs) < 100:
                    break
                    
                before = msgs[-1]['id']
                await asyncio.sleep(0.1)
                
            return filtered

        try:
            return self.run_async(_async_get_since())
        except Exception as e:
            print(f"❌ Erro em get_messages_since_date: {e}")
            return []

    # ----------------------------
    # SUPER LOTE: Agora com proteções extremas
    # ----------------------------
    async def _super_lote_get_all_messages(self, channel: Dict, initial_before: Optional[str] = None):
        channel_id = channel['id']
        super_lote = []
        before = initial_before  # Use o 'before' passado para continuar
        reached_end = False
        accumulated = 0
        page = 0
        # deque para controlar visto de cursors
        seen_befores = deque(maxlen=SEEN_BEFORES_MAXLEN)
        consecutive_empty = 0  # Novo: detecta API travada

        print(f"\n[Super Lote] Iniciando busca em: {channel.get('name', 'DM')} a partir de {before if before else 'início'}")
        print(f"   Carregando até {SUPER_LOTE_SIZE} mensagens do usuário...")

        while len(super_lote) < SUPER_LOTE_SIZE and page < MAX_PAGES_PER_LOTE:
            if self._stop_event.is_set():
                print("⏹️ Stop event set — interrompendo super lote.")
                reached_end = False
                break

            page += 1
            params = {'limit': 100}
            if before:
                params['before'] = before
            data = await self.async_api_request('GET', f'{API_BASE}/channels/{channel_id}/messages', params=params)

            if not data:
                consecutive_empty += 1
                if consecutive_empty >= 3:
                    print("   3 páginas vazias consecutivas. Finalizando lote.")
                    reached_end = True
                    break
                await asyncio.sleep(1)
                continue

            consecutive_empty = 0
            last_id = data[-1]['id']
            if last_id in seen_befores:
                print("   Cursor repetido detectado; evitando loop infinito.")
                reached_end = True
                break
            seen_befores.append(last_id)

            user_msgs = [
                m for m in data
                if m.get('author', {}).get('id') == self.user_id
                and not m.get('pinned', False)
                and m.get('type') in [0, 19]
            ]

            super_lote.extend(user_msgs)
            accumulated += len(user_msgs)
            before = last_id  # Atualize 'before' com o último da página

            if accumulated % 200 == 0 and accumulated > 0:
                print(f"   Encontradas {accumulated} mensagens do usuário até agora...", end='\r')

            # GC forçado a cada 2 páginas
            if page % 2 == 0:
                gc.collect()
                self.stats['gc_forced_count'] += 1

            await asyncio.sleep(random.uniform(0.5, 1.0))  # Delay aumentado

            if len(data) < 100:
                print(f"   Página incompleta (<100 mensagens). Fim do canal detectado.")
                reached_end = True
                break

        print(f"   Lote carregado: {len(super_lote)} mensagens do usuário (páginas: {page})")

        # Limpeza final
        del data, user_msgs
        gc.collect()

        return super_lote, before, reached_end

    # ----------------------------
    # Message deletion
    # ----------------------------
    async def async_delete_single_message(self, channel_id: str, message_id: str, max_retries: int = 5):
        """Deleta uma mensagem com backoff exponencial agressivo em 429s"""
        url = f'{API_BASE}/channels/{channel_id}/messages/{message_id}'
        attempt = 0
        consecutive_429 = 0  # Contador de 429s consecutivos
        
        while attempt < max_retries:
            if self._stop_event.is_set():
                print("⏹️ Stop event set — abortando delete single.")
                return False
            attempt += 1
            try:
                # CORREÇÃO: Inicialização thread-safe do semáforo
                if self._semaphore is None:
                    with self._semaphore_lock:
                        if self._semaphore is None:  # Double-check locking
                            self._semaphore = asyncio.Semaphore(self.max_concurrent_requests)
                async with self._semaphore:
                    self.before_request()
                    resp = await asyncio.wait_for(self.async_client.delete(url), timeout=HTTP_REQUEST_TIMEOUT)
                    self.after_request()
                    
                if resp.status_code in (200, 204):
                    return True
                    
                if resp.status_code == 429:
                    consecutive_429 += 1
                    self.stats['throttled_count'] += 1
                    
                    # Pegar retry_after da resposta
                    retry_after = 5.0  # Padrão mais alto
                    try:
                        body = resp.json()
                        retry_after = float(body.get('retry_after', retry_after))
                    except Exception:
                        try:
                            retry_after = float(resp.headers.get('retry-after', retry_after) or retry_after)
                        except:
                            pass
                    
                    self.stats['throttled_total_time'] += retry_after
                    
                    # BACKOFF EXPONENCIAL AGRESSIVO: base * 2^attempt
                    base_wait = max(retry_after, 3.0)  # Mínimo 3 segundos
                    exponential_wait = base_wait * (2 ** (attempt - 1))  # 3, 6, 12, 24, 48...
                    wait = min(exponential_wait, 120)  # Cap em 2 minutos
                    
                    print(f"⚠️ 429 ao deletar msg {message_id}. Backoff exponencial: {wait:.1f}s (attempt {attempt}/{max_retries}).")
                    await asyncio.sleep(wait)
                    
                    # COOLDOWN GLOBAL após múltiplos 429s
                    if consecutive_429 >= CONSECUTIVE_429_COOLDOWN_THRESHOLD:
                        print(f"🚨 {consecutive_429} 429s consecutivos! Cooldown de {COOLDOWN_AFTER_429_BURST}s...")
                        await asyncio.sleep(COOLDOWN_AFTER_429_BURST)
                        consecutive_429 = 0  # Reset contador
                    
                    continue

                # 404 = já deletada, 403 = permissão
                if resp.status_code == 404:
                    return True
                if resp.status_code == 403:
                    print(f"❌ Sem permissão para deletar mensagem {message_id} (HTTP 403). Pulando.")
                    return False

                print(f"❌ Erro ao deletar mensagem {message_id}: HTTP {resp.status_code} - {resp.text}")
                return False
                
            except asyncio.TimeoutError:
                wait = 2.0 * (2 ** (attempt - 1))  # Backoff exponencial
                print(f"⚠️ Timeout ao deletar (attempt {attempt}/{max_retries}). Esperando {wait:.1f}s.")
                await asyncio.sleep(wait)
            except httpx.RequestError as e:
                wait = 2.0 * (2 ** (attempt - 1))  # Backoff exponencial
                print(f"⚠️ httpx.RequestError ao deletar (attempt {attempt}/{max_retries}): {e}. Esperando {wait:.1f}s.")
                await asyncio.sleep(wait)
            except Exception as e:
                print(f"❌ Exceção ao deletar mensagem {message_id}: {e}")
                traceback.print_exc()
                return False
        return False

    async def async_safe_delete_messages(
            self,
            messages: List,
            channel: Dict,
            delay_range=(2.5, 4.5),  # AUMENTADO: delay padrão mais seguro para evitar 429
            progress_callback: Optional[Callable] = None
        ):
        """ 
        Deleta mensagens respeitando o delay configurado (min_delay, max_delay) passado pelo app.
        Executa em sequência para evitar rate limits.
        """
        deleted = 0
        total = len(messages)
        channel_id = channel['id']
        channel_name = channel.get('name', channel.get('server_name', 'Canal'))

        for idx, msg in enumerate(messages):
            if self._stop_event.is_set():
                print("⏹️ Stop event set — abortando safe_delete_messages.")
                break

            # safety: observe cap global de deleções - com validação
            if self.max_total_deletes is not None:
                if self.max_total_deletes <= 0:  # Validação para evitar trava
                    print("⚠️ max_total_deletes inválido (<=0). Parando deleções.")
                    break
                if self.stats['deleted_count'] >= self.max_total_deletes:
                    print("⚠️ Cap global de deleções atingido; abortando remoções adicionais.")
                    break

            if progress_callback:
                try:
                    progress_callback(idx + 1, total, channel_name)
                except Exception as e:
                    print(f"⚠️ Erro no progress_callback: {e}")  # Loga em vez de silenciar

            success = await self.async_delete_single_message(channel_id, msg['id'])
            if success:
                self.stats['deleted_count'] += 1
                deleted += 1
            else:
                self.stats['failed_count'] += 1

            # GC forçado periodicamente
            if self.stats['deleted_count'] % FORCE_GC_INTERVAL == 0 and self.stats['deleted_count'] > 0:
                gc.collect()
                self.stats['gc_forced_count'] += 1

            # Delay real definido pelo usuário (respeita min e max)
            delay = random.uniform(*delay_range)
            await asyncio.sleep(delay)

        return deleted

    def safe_delete_messages(self, messages, channel, delay_range=(1.8, 3.5), progress_callback=None):
        return self.run_async(self.async_safe_delete_messages(messages, channel, delay_range=delay_range, progress_callback=progress_callback))

    async def async_get_dms(self):
        data = await self.async_api_request('GET', f'{API_BASE}/users/@me/channels')
        return data or []

    def get_stats(self):
        return self.stats.copy()

    def reset_stats(self):
        self.stats['deleted_count'] = 0
        self.stats['failed_count'] = 0
        self.stats['throttled_count'] = 0
        self.stats['throttled_total_time'] = 0.0
        self.stats['last_ping'] = 0.0
        self.stats['avg_ping'] = 0.0
        self.stats['gc_forced_count'] = 0

    # ----------------------------
    # NOVO MÉTODO - Async channel processing (para modo massa)
    # ----------------------------
    async def async_process_channels(self):
        """ 
        Processa canais buscando e deletando em ciclos para evitar travamentos em históricos grandes.
        - Usa apenas métodos async internamente (sem wrappers síncronos)
        - Proteções contra loops infinitos
        - Recria cliente HTTP periodicamente para evitar leaks
        - GC forçado regularmente
        """
        print("\n🔄 Buscando lista de DMs (pode demorar se houver muitas)...")
        try:
            raw_dms = await self.async_get_dms()
        except Exception as e:
            print(f"❌ Falha ao buscar DMs: {e}")
            return 0

        # Formata os DMs como fazia get_dms()
        formatted_dms = []
        for dm in raw_dms:
            recipients = [r for r in dm.get('recipients', []) if r.get('id') != self.user_id]
            dm_info = {
                'id': dm['id'],
                'name': 'DM',
                'username': '',
                'avatar': None,
                'type': 'dm' if dm.get('type') == 1 else 'group',
                'last_message_id': dm.get('last_message_id', '0')
            }
            if recipients:
                recipient = recipients[0]
                dm_info['user_id'] = recipient.get('id')
                dm_info['name'] = recipient.get('global_name', recipient.get('username', 'Unknown User'))
                dm_info['username'] = recipient.get('username', 'unknown')
                dm_info['avatar'] = recipient.get('avatar')
            formatted_dms.append(dm_info)

        formatted_dms.sort(key=lambda x: int(x['last_message_id'] or 0), reverse=True)
        seen = set()
        unique_dms = []
        for dm_info in formatted_dms:
            uid = dm_info.get('user_id', dm_info['id'])
            if uid not in seen:
                seen.add(uid)
                unique_dms.append(dm_info)

        # Limite prudente inicial (evita processar 1000s de DMs por vez)
        active_dms = unique_dms[:50]
        print(f"\n📊 DMs encontradas: {len(unique_dms)} (Processando as {len(active_dms)} mais recentes)")

        processed_channels_count = 0
        total_dms = len(active_dms)

        for index, dm in enumerate(active_dms):
            if self._stop_event.is_set():
                print("⏹️ Stop event set — interrompendo processamento de canais.")
                break

            channel_name = dm.get('name', 'DM Desconhecida')
            print(f"\n ▶️ [{index + 1}/{total_dms}] Iniciando canal: {channel_name}")

            total_deleted_in_channel = 0
            has_more_messages = True
            before = None  # Inicialize 'before' para paginar entre super lotes

            # Proteção por canal: qualquer exceção deve marcar o canal como concluído e seguir em frente
            try:
                while has_more_messages and not self._stop_event.is_set():
                    print(f"   Buscando super lote de até {SUPER_LOTE_SIZE} mensagens (antes de {before if before else 'início'})...")
                    batch_msgs, new_before, reached_end = await self._super_lote_get_all_messages(dm, initial_before=before)
                    before = new_before

                    count = len(batch_msgs)
                    print(f"   Encontradas {count} mensagens para deletar neste super lote.")

                    if count == 0:
                        if reached_end:
                            print("   Fim do canal alcançado sem mais mensagens.")
                            has_more_messages = False
                        else:
                            print("   Lote vazio, mas não fim do canal. Continuando para próximo lote.")
                        continue

                    # Deletar em blocos menores para evitar longos bloqueios
                    for start in range(0, len(batch_msgs), CHUNK_SIZE):
                        if self._stop_event.is_set():
                            print("⏹️ Stop event set dentro do loop de chunks — abortando chunk deletions.")
                            break
                        chunk_msgs = batch_msgs[start: start + CHUNK_SIZE]
                        deleted = await self.async_safe_delete_messages(
                            chunk_msgs,
                            dm,
                            delay_range=(1.8, 3.5),  # Delay seguro
                            progress_callback=lambda idx, tot, name:
                                print(f"      Deletando {idx}/{tot} do chunk atual...", end='\r')
                        )
                        total_deleted_in_channel += deleted
                        print(f"\n   Chunk finalizado. Total no canal até agora: {total_deleted_in_channel}")
                        # pequeno descanso entre chunks
                        await asyncio.sleep(2.0)  # Aumentado

                        # GC após cada chunk
                        gc.collect()

                    # Proteção curta entre super lotes
                    await asyncio.sleep(3.0)  # Aumentado

                    if reached_end:
                        has_more_messages = False

                processed_channels_count += 1
                print(f"🏁 Canal {channel_name} finalizado. Total deletado nesse canal: {total_deleted_in_channel}")

            except Exception as e:
                print(f"⚠️ Erro ao processar canal {channel_name}: {e}")
                traceback.print_exc()
                # continue com próximos canais
                continue

            # Pequena pausa entre canais
            await asyncio.sleep(2.0)  # Aumentado

            # Reinicialize cliente HTTP a cada N canais para recuperar conexões
            if processed_channels_count % CLIENT_RECREATE_INTERVAL == 0:
                print("🔧 Manutenção: Recriando AsyncClient para liberar recursos...")
                try:
                    self.setup_api_session()
                except Exception as e:
                    print(f"⚠️ Erro ao recriar client durante manutenção: {e}")
                await asyncio.sleep(3.0)
                gc.collect()

        # GC final
        gc.collect()
        return processed_channels_count


    # ----------------------------
    # Cleanup
    # ----------------------------
    def cleanup(self):
        """Fecha recursos - com fechamento do loop se possível"""
        print("🧹 Limpando recursos...")
        # Sinaliza stop para tasks async
        self._stop_event.set()

        # fecha selenium driver
        if self.driver:
            try:
                self.driver.quit()
                self.driver = None
            except Exception:
                pass

        # --- CORREÇÃO: REMOÇÃO DO DIRETÓRIO TEMPORÁRIO DO CHROME ---
        # Usa o caminho salvo em self.temp_user_data_dir (criado em setup_selenium)
        if hasattr(self, 'temp_user_data_dir') and self.temp_user_data_dir and os.path.exists(self.temp_user_data_dir):
            try:
                # O shutil.rmtree remove o diretório e todo o seu conteúdo
                shutil.rmtree(self.temp_user_data_dir, ignore_errors=True)
                print(f"🧹 Pasta temporária removida: {self.temp_user_data_dir}")
            except Exception as e:
                print(f"⚠️ Erro ao remover temp dir: {e}")
        # -------------------------------------------------------------

        # fecha o async client de forma segura
        try:
            self._close_async_client(timeout=CLIENT_CLOSE_TIMEOUT)
        except Exception as e:
            print(f"⚠️ Erro ao fechar async client: {e}")

        # cancela e aguarda tasks no loop (graceful)
        if self.loop and self._loop_thread.is_alive():
            async def _cancel_all_tasks():
                try:
                    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
                    if not tasks:
                        return
                    for t in tasks:
                        t.cancel()
                    results = await asyncio.gather(*tasks, return_exceptions=True)
                    return results
                except Exception as e:
                    print(f"⚠️ Erro no cancel_all_tasks: {e}")
                    return None

            try:
                fut = asyncio.run_coroutine_threadsafe(_cancel_all_tasks(), self.loop)
                try:
                    fut.result(timeout=15)
                except Exception as e:
                    print(f"⚠️ Timeout/erro aguardando cancel_all_tasks: {e}")
                # pare o loop depois de cancelar tasks
                self.loop.call_soon_threadsafe(self.loop.stop)
                self._loop_thread.join(timeout=5)
            except Exception as e:
                print(f"⚠️ Erro durante shutdown gracioso do loop: {e}")

        # GC final forçado
        gc.collect()
        print("✅ Cleanup concluído")

# ----------------------------
# Função principal (demo/shell) - com tratamento de KeyboardInterrupt async
# ----------------------------
def _install_signal_handler(deleter: DiscordMessageDeleter):
    """Instala handler de SIGINT que seta o stop_event e tenta um shutdown gracioso."""
    def _handler(sig, frame):
        print("\n🛑 SIGINT recebido — sinalizando parada. Tentando shutdown gracioso...")
        deleter._stop_event.set()
    try:
        signal.signal(signal.SIGINT, _handler)
    except Exception as e:
        print(f"⚠️ Não foi possível instalar signal handler: {e}")

@contextmanager
def async_signal_handler(signum, frame):
    """Context manager para compatibilidade (mantido para compatibilidade com código antigo)"""
    old_handler = signal.getsignal(signum)
    signal.signal(signum, lambda s, f: None)  # Ignora sinal durante execução
    try:
        yield
    finally:
        signal.signal(signum, old_handler)

def main():
    deleter = DiscordMessageDeleter(max_concurrent_requests=MAX_CONCURRENT_REQUESTS, fetch_all_by_default=True)
    _install_signal_handler(deleter)

    try:
        print("🚀 Discord Message Deleter - VERSÃO FINAL ESTÁVEL")
        print("=" * 60)

        email = input("📧 Email: ")
        password = input("🔒 Senha: ")

        result = deleter.login(email, password)

        if result:
            print("✅ Login realizado com sucesso!")
            # Aguarda um pouco após login bem-sucedido
            time.sleep(random.uniform(5, 10))

            print("👤 Informações do usuário:")
            print(f" ID: {deleter.user_id}")
            print(f" Nome: {deleter.user_info.get('global_name', deleter.user_info.get('username', 'N/A'))}")
            print(f" Email: {deleter.user_info.get('email', 'N/A')}")

            # Processa os canais usando o loop persistente - com handler para interrupt
            print("\n🔥 Iniciando processamento de canais (DMs e Servidores)...")
            deleter.stats['start_time'] = time.time()

            # Executa a corrotina principal no loop em thread e aguarda resultado
            try:
                processed_channels = deleter.run_async(deleter.async_process_channels(), timeout=None)
            except KeyboardInterrupt:
                print("\n⏹️ Operação cancelada pelo usuário (KeyboardInterrupt).")
                processed_channels = 0
            except Exception as e:
                print(f"\n❌ Erro ao processar canais: {e}")
                traceback.print_exc()
                processed_channels = 0

            elapsed = time.time() - deleter.stats['start_time']
            stats = deleter.get_stats()

            print("\n✨ Resultado Final:")
            print("=" * 60)
            print(f"📊 Canais processados: {processed_channels}")
            print(f"💭 Mensagens deletadas: {stats['deleted_count']:,}")
            print(f"❌ Falhas: {stats['failed_count']:,}")
            print(f"⚠️ Rate limits: {stats['throttled_count']:,}")
            print(f"⏱️ Tempo total: {elapsed/60:.1f} minutos")
            print(f"🔄 Clientes recriados: {stats['client_recreate_count']}")
            print(f"🧹 GC forçado: {stats['gc_forced_count']} vezes")
            print(f"📈 Ping médio: {stats['avg_ping']:.0f}ms")
            print("=" * 60)

        else:
            print("❌ Falha no login.")

    except KeyboardInterrupt:
        print("\n⏹️ Operação cancelada pelo usuário")
    except Exception as e:
        print(f"\n❌ Erro fatal: {e}")
        traceback.print_exc()
    finally:
        deleter.cleanup()

if __name__ == "__main__":
    main()
