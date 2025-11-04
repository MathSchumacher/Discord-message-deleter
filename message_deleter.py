# message_deleter.py
import os
import time
import json
import random
import re
from datetime import datetime, timedelta, timezone
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import requests
import tls_client
import shutil

class DiscordMessageDeleter:
    def __init__(self):
        self.driver = None
        self.token = None
        self.session = None
        self.headers = None
        self.user_id = None
        self.user_info = None
        self.stats = {
            'start_time': None,
            'deleted_count': 0,
            'failed_count': 0,
            'throttled_count': 0,
            'throttled_total_time': 0,
            'last_ping': 0,
            'avg_ping': 0
        }

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

    def setup_selenium(self):
        """Configura o Selenium WebDriver com Google Chrome"""
        try:
            chrome_paths = [
                'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
                'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe',
                os.path.expanduser('~\\AppData\\Local\\Google\\Chrome\\Application\\chrome.exe')
            ]
            
            chrome_path = None
            for path in chrome_paths:
                if os.path.exists(path):
                    chrome_path = path
                    break
            
            options = Options()
            if chrome_path:
                options.binary_location = chrome_path
                print(f"✅ Chrome encontrado em: {chrome_path}")
            
            options.add_argument("--disable-blink-features=AutomationControlled")
            options.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
            options.add_experimental_option('useAutomationExtension', False)
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--disable-gpu")
            options.add_argument("--disable-web-security")
            options.add_argument("--allow-running-insecure-content")
            options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
            
            temp_dir = os.path.join(os.getcwd(), f"chrome_temp_{int(time.time())}_{random.randint(1000, 9999)}")
            options.add_argument(f"--user-data-dir={temp_dir}")
            
            print("🚀 Inicializando Chrome...")
            self.driver = webdriver.Chrome(options=options)
            
            self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            self.driver.execute_cdp_cmd('Network.setUserAgentOverride', {
                "userAgent": 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            })
            
            print("✅ Chrome inicializado com sucesso")
            return self.driver
            
        except Exception as e:
            print(f"❌ Erro ao configurar Chrome: {e}")
            return None

    def wait_for_login_success(self, timeout=90):
        """Aguarda o login ser bem-sucedido com múltiplas estratégias"""
        print("⏳ Aguardando confirmação de login...")
        
        start_time = time.time()
        while time.time() - start_time < timeout:
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
                
                error_indicators = [
                    "//div[contains(text(), 'Invalid login')]",
                    "//div[contains(text(), 'Wrong email')]",
                    "//div[contains(text(), 'Wrong password')]",
                    "//div[contains(text(), 'Login inválido')]",
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
                
                time.sleep(2)
                
            except Exception as e:
                print(f"⚠️ Erro durante verificação de login: {e}")
                time.sleep(2)
        
        print("❌ Timeout na verificação de login")
        return False

    def login(self, email, password):
        """Login melhorado com tratamento robusto de erros"""
        print("🔄 Iniciando processo de login no Discord...")
        
        if not self.setup_selenium():
            print("❌ Falha ao configurar Chrome")
            return False
        
        try:
            self.driver.get('https://discord.com/login')
            time.sleep(5)
            
            print("📧 Preenchendo email...")
            try:
                email_input = WebDriverWait(self.driver, 20).until(
                    EC.presence_of_element_located((By.NAME, "email"))
                )
                email_input.clear()
                email_input.send_keys(email)
                print("✅ Email preenchido")
            except TimeoutException:
                print("❌ Campo de email não encontrado")
                return False
            
            print("🔒 Preenchendo senha...")
            try:
                password_input = self.driver.find_element(By.NAME, "password")
                password_input.clear()
                password_input.send_keys(password)
                print("✅ Senha preenchida")
            except NoSuchElementException:
                print("❌ Campo de senha não encontrado")
                return False
            
            print("🚀 Clicando em login...")
            try:
                submit_button = self.driver.find_element(By.XPATH, "//button[@type='submit']")
                submit_button.click()
                print("✅ Botão de login clicado")
            except NoSuchElementException:
                print("❌ Botão de login não encontrado")
                return False
            
            login_result = self.wait_for_login_success(60)
            
            if login_result == "2FA_REQUIRED":
                print("🔐 2FA detectado. Aguardando código manual...")
                input_code = input("📱 Digite o código 2FA: ")
                
                try:
                    code_input = WebDriverWait(self.driver, 15).until(
                        EC.presence_of_element_located((By.NAME, "code"))
                    )
                    code_input.clear()
                    code_input.send_keys(input_code)
                    
                    submit_buttons = self.driver.find_elements(By.XPATH, "//button[@type='submit']")
                    for button in submit_buttons:
                        try:
                            button.click()
                            break
                        except:
                            continue
                    
                    login_result = self.wait_for_login_success(30)
                    
                except TimeoutException:
                    print("❌ Timeout no 2FA")
                    return False
            
            if login_result is True:
                print("✅ Login bem-sucedido! Obtendo token...")
                time.sleep(8)
                
                max_attempts = 5
                for attempt in range(max_attempts):
                    print(f"🔄 Tentativa {attempt + 1}/{max_attempts} de obter token...")
                    self.token = self.get_discord_token_safe()
                    
                    if self.token:
                        print("✅ Token obtido com sucesso")
                        break
                    time.sleep(3)
                
                if not self.token:
                    print("❌ Não foi possível obter o token")
                    return False
                
                # Mantém o navegador aberto para funcionalidade
                self.setup_api_session()
                self.user_info = self.get_user_info()
                
                if self.user_info:
                    self.user_id = self.user_info['id']
                    print(f"👤 Usuário autenticado: {self.user_info.get('global_name', self.user_info.get('username', 'N/A'))}")
                    return True
                else:
                    print("❌ Token inválido ou expirado")
                    return False
                    
            else:
                print("❌ Falha no login - credenciais inválidas ou timeout")
                return False
            
        except Exception as e:
            print(f"❌ Erro durante o login: {e}")
            return False

    def setup_api_session(self):
        """Configura sessão API com headers apropriados"""
        self.session = tls_client.Session(
            client_identifier="chrome_131", 
            random_tls_extension_order=True
        )
        
        self.headers = {
            'authorization': self.token,
            'content-type': 'application/json',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'x-discord-timezone': 'America/Sao_Paulo',
        }

    def before_request(self):
        self.stats['_before_ts'] = time.time() * 1000

    def after_request(self):
        if hasattr(self, 'stats') and '_before_ts' in self.stats:
            ping = (time.time() * 1000) - self.stats['_before_ts']
            self.stats['last_ping'] = ping
            self.stats['avg_ping'] = self.stats['avg_ping'] * 0.9 + ping * 0.1 if self.stats['avg_ping'] > 0 else ping

    def safe_api_get(self, url, params=None, delay=1.0):
        """API call com delays protetivos"""
        time.sleep(delay)
        return self.api_get(url, params)

    def api_get(self, url, params=None):
        """Método genérico para GET com handling de rate limit"""
        while True:
            self.before_request()
            response = self.session.get(url, headers=self.headers, params=params)
            self.after_request()
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 429:
                self.stats['throttled_count'] += 1
                retry_after = response.json().get('retry_after', 1)
                self.stats['throttled_total_time'] += retry_after
                print(f"⚠️ Rate limit hit. Waiting {retry_after} seconds.")
                time.sleep(retry_after)
            else:
                raise Exception(f"API error: {response.status_code} {response.text}")

    def get_user_info(self):
        try:
            return self.safe_api_get('https://discord.com/api/v9/users/@me', delay=1.0)
        except Exception as e:
            print(f"❌ Exceção ao obter info usuário: {e}")
            return None
    
    def get_dms(self, limit=20):
        try:
            dms = self.safe_api_get('https://discord.com/api/v9/users/@me/channels', delay=1.5)
            formatted_dms = []
            
            for dm in dms[:limit]:  # Limita o número de DMs
                if 'recipients' in dm and dm['recipients']:
                    for recipient in dm['recipients']:
                        if recipient.get('id') == self.user_id:
                            continue
                        
                        dm_info = {
                            'id': dm['id'],
                            'user_id': recipient.get('id'),
                            'name': recipient.get('global_name', recipient.get('username', 'Unknown User')),
                            'username': recipient.get('username', 'unknown'),
                            'discriminator': recipient.get('discriminator', '0'),
                            'avatar': recipient.get('avatar'),
                            'type': 'dm'
                        }
                        formatted_dms.append(dm_info)
            
            return formatted_dms
        except Exception as e:
            print(f"❌ Exceção ao obter DMs: {e}")
            return []

    def get_servers(self, limit=15):
        try:
            servers = self.safe_api_get('https://discord.com/api/v9/users/@me/guilds', delay=1.5)
            return servers[:limit]  # Limita servidores
        except Exception as e:
            print(f"❌ Exceção ao obter servidores: {e}")
            return []

    def get_server_channels(self, server_id, limit=10):
        try:
            channels = self.safe_api_get(f'https://discord.com/api/v9/guilds/{server_id}/channels', delay=1.0)
            text_channels = [ch for ch in channels if ch['type'] in [0, 5]][:limit]  # 0: text, 5: announcement
            return text_channels
        except Exception as e:
            print(f"❌ Exceção ao obter canais do servidor {server_id}: {e}")
            return []

    def fetch_messages(self, channel_id, limit=50, before=None, after=None):
        """Função auxiliar para buscar mensagens de um canal com paginação segura"""
        messages = []
        params = {'limit': min(limit, 50)}  # Limite reduzido
        if before:
            params['before'] = before
        if after:
            params['after'] = after
        url = f'https://discord.com/api/v9/channels/{channel_id}/messages'
        
        try:
            data = self.safe_api_get(url, params, delay=1.0)
            if data:
                messages.extend(data)
        except Exception as e:
            print(f"❌ Error fetching messages: {e}")
        
        return messages[:limit]

    def get_all_user_messages(self, channel, limit=100):
        """Obtém mensagens do usuário no canal com limite seguro"""
        channel_id = channel['id']
        all_messages = self.fetch_messages(channel_id, limit=limit * 2)  # Busca um pouco mais
        user_messages = [msg for msg in all_messages if msg['author']['id'] == self.user_id and not msg.get('pinned', False)]
        return user_messages[:limit]

    def get_messages_since_date(self, channel, since_date, limit=100):
        """Obtém mensagens do usuário desde uma data específica com limite"""
        channel_id = channel['id']
        since_date = since_date.replace(tzinfo=timezone.utc)
        all_messages = self.fetch_messages(channel_id, limit=limit * 2)
        filtered_messages = [msg for msg in all_messages if msg['author']['id'] == self.user_id and datetime.fromisoformat(msg['timestamp'].replace('Z', '+00:00')) > since_date and not msg.get('pinned', False)]
        return filtered_messages[:limit]

    def get_messages_between_dates(self, channel, start_date, end_date, limit=100):
        """Obtém mensagens do usuário entre datas específicas com limite"""
        channel_id = channel['id']
        start_date = datetime.combine(start_date, datetime.min.time()).replace(tzinfo=timezone.utc)
        end_date = datetime.combine(end_date, datetime.max.time()).replace(tzinfo=timezone.utc)
        all_messages = self.fetch_messages(channel_id, limit=limit * 2)
        filtered_messages = [msg for msg in all_messages if msg['author']['id'] == self.user_id and start_date <= datetime.fromisoformat(msg['timestamp'].replace('Z', '+00:00')) <= end_date and not msg.get('pinned', False)]
        return filtered_messages[:limit]

    def get_user_messages(self, channel, limit=50):
        """Obtém as últimas X mensagens do usuário no canal com limite seguro"""
        channel_id = channel['id']
        all_messages = self.fetch_messages(channel_id, limit=limit * 3)
        user_messages = [msg for msg in all_messages if msg['author']['id'] == self.user_id and not msg.get('pinned', False)]
        return user_messages[:limit]

    def safe_delete_messages(self, messages, channel, delay_range=(2.0, 5.0), progress_callback=None):
        """Deleta mensagens com delays maiores para evitar rate limits"""
        deleted = 0
        channel_id = channel['id']
        channel_name = channel.get('name', channel.get('server_name', 'Canal'))
        total = len(messages)
        
        for idx, msg in enumerate(messages):
            if progress_callback:
                progress_callback(idx + 1, total, channel_name)
            
            max_retries = 2
            for attempt in range(max_retries):
                try:
                    url = f'https://discord.com/api/v9/channels/{channel_id}/messages/{msg["id"]}'
                    self.before_request()
                    response = self.session.delete(url, headers=self.headers)
                    self.after_request()
                    
                    if response.status_code in [200, 204]:
                        self.stats['deleted_count'] += 1
                        deleted += 1
                        break
                    elif response.status_code == 429:
                        self.stats['throttled_count'] += 1
                        retry_after = response.json().get('retry_after', 2)
                        self.stats['throttled_total_time'] += retry_after
                        print(f"⚠️ Rate limit. Waiting {retry_after} seconds.")
                        time.sleep(retry_after)
                    else:
                        if response.status_code == 403:
                            print(f"❌ Permissão negada para deletar mensagem em {channel_name}")
                        break
                except Exception as e:
                    print(f"❌ Attempt {attempt+1} failed: {e}")
                    if attempt == max_retries - 1:
                        self.stats['failed_count'] += 1
                    time.sleep(2 ** attempt)
            
            # Delay maior entre deleções
            time.sleep(random.uniform(*delay_range))
        
        return deleted

    def simulate_human_behavior(self):
        """Simula comportamento humano entre operações"""
        time.sleep(random.uniform(3, 7))
        if self.driver:
            try:
                # Scroll aleatório suave
                self.driver.execute_script("window.scrollBy(0, 200);")
            except:
                pass

    def get_stats(self):
        """Retorna as estatísticas atuais"""
        return self.stats.copy()

    def reset_stats(self):
        """Reseta as estatísticas"""
        self.stats['deleted_count'] = 0
        self.stats['failed_count'] = 0
        self.stats['throttled_count'] = 0
        self.stats['throttled_total_time'] = 0

    def cleanup(self):
        """Limpa recursos"""
        if self.driver:
            try:
                self.driver.quit()
            except:
                pass
        if self.session:
            try:
                self.session.close()
            except:
                pass

def main():
    deleter = DiscordMessageDeleter()
    
    try:
        print("🚀 Discord Message Deleter")
        print("=" * 50)
        
        email = input("📧 Email: ")
        password = input("🔒 Senha: ")
        
        result = deleter.login(email, password)
        
        if result:
            print("✅ Login realizado com sucesso!")
            
            print("👤 Informações do usuário:")
            print(f"   ID: {deleter.user_id}")
            print(f"   Nome: {deleter.user_info.get('global_name', deleter.user_info.get('username', 'N/A'))}")
            print(f"   Email: {deleter.user_info.get('email', 'N/A')}")
            
            print("\n📥 Carregando DMs e servidores...")
            dms = deleter.get_dms()
            servers = deleter.get_servers()
            
            print(f"💬 DMs encontradas: {len(dms)}")
            print(f"🏠 Servidores encontrados: {len(servers)}")
            
            if dms:
                print("\n📋 Primeiras 5 DMs:")
                for dm in dms[:5]:
                    print(f"   👤 {dm['name']} (@{dm['username']})")
            
            if servers:
                print("\n🏠 Primeiros 5 servidores:")
                for server in servers[:5]:
                    owner_flag = " 👑" if server.get('owner') else ""
                    print(f"   🏠 {server['name']}{owner_flag}")
            
            # Simula comportamento humano
            deleter.simulate_human_behavior()
            
        else:
            print("❌ Falha no login.")
            
    except KeyboardInterrupt:
        print("\n⏹️  Operação cancelada")
    except Exception as e:
        print(f"❌ Erro: {e}")
    finally:
        deleter.cleanup()

if __name__ == "__main__":
    main()