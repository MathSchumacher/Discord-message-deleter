# app.py
import streamlit as st
import pandas as pd
import time
import random
from datetime import datetime, timedelta
import sys
import os
import queue
from concurrent.futures import ThreadPoolExecutor
import asyncio
from message_deleter import DiscordMessageDeleter
import base64
import requests
from io import BytesIO
from PIL import Image
import traceback

# Configuração da página
st.set_page_config(
    page_title="Discord Message Cleaner",
    page_icon="🗑️", # Este é o ícone da ABA do navegador
    layout="wide",
    initial_sidebar_state="expanded"
)

# CSS customizado
st.markdown("""
<style>
    /* --- INÍCIO DA MODIFICAÇÃO --- */
    /* Importa a biblioteca Font Awesome para usar os ícones */
    @import url('https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.2/css/all.min.css');
    /* --- FIM DA MODIFICAÇÃO --- */

    .main-header {
        font-size: 2.5rem;
        color: #5865F2;
        text-align: center;
        margin-bottom: 2rem;
    }
    .channel-card {
        padding: 1rem;
        border-radius: 10px;
        border: 1px solid #ddd;
        margin: 0.5rem 0;
        background-color: #f8f9fa;
    }
    .success-box {
        background-color: #d4edda;
        border: 1px solid #c3e6cb;
        border-radius: 5px;
        padding: 1rem;
        color: #155724;
    }
    .warning-box {
        background-color: #fff3cd;
        border: 1px solid #ffeaa7;
        border-radius: 5px;
        padding: 1rem;
        color: #856404;
    }
    .error-box {
        background-color: #f8d7da;
        border: 1px solid #f5c6cb;
        border-radius: 5px;
        padding: 1rem;
        color: #721c24;
    }
    .info-box {
        background-color: #d1ecf1;
        border: 1px solid #bee5eb;
        border-radius: 5px;
        padding: 1rem;
        color: #0c5460;
    }
    .avatar-img {
        border-radius: 50%;
        width: 40px;
        height: 40px;
    }
    .stats-card {
        background: linear-gradient(45deg, #5865F2, #7289DA);
        color: white;
        padding: 1rem;
        border-radius: 10px;
        text-align: center;
    }
    .filter-section {
        background-color: #f8f9fa;
        border-radius: 10px;
        padding: 1rem;
        margin: 1rem 0;
        border-left: 4px solid #5865F2;
    }
    .login-box {
        background-color: #f8f9fa;
        border-radius: 15px;
        padding: 2rem;
        margin: 1rem 0;
        border: 2px solid #5865F2;
    }
    .server-container {
        margin-bottom: 0.5rem;
    }
    .channel-list {
        padding-left: 20px;
        margin-top: 5px;
    }
    .compact-channel {
        margin-bottom: 4px;
        padding: 2px 0;
    }
    .donation-container {
        position: relative;
        display: inline-block;
    }
    .donation-dropdown {
        position: absolute;
        top: 100%;
        right: 0;
        background-color: #f8f9fa;
        border: 1px solid #ddd;
        border-radius: 10px;
        padding: 1rem;
        z-index: 1000;
        box-shadow: 0 4px 8px rgba(0,0,0,0.1);
        text-align: center;
        width: 200px;
    }
    .donation-button {
        background-color: #5865F2;
        color: white;
        border: none;
        padding: 0.5rem 1rem;
        border-radius: 5px;
        cursor: pointer;
    }
    .copy-button {
        background-color: #28a745;
        color: white;
        border: none;
        padding: 0.5rem 1rem;
        border-radius: 5px;
        cursor: pointer;
        margin-top: 0.5rem;
    }
</style>
""", unsafe_allow_html=True)


# --- INÍCIO DAS FUNÇÕES DE CACHE ---
# Cache de 5 minutos (300 segundos)

@st.cache_data(ttl=300)
def get_cached_dms(_deleter_instance):
    """Busca e armazena em cache a lista de DMs"""
    print("CACHE MISS: Buscando DMs da API")
    return _deleter_instance.get_dms()

@st.cache_data(ttl=300)
def get_cached_servers(_deleter_instance):
    """Busca e armazena em cache a lista de Servidores"""
    print("CACHE MISS: Buscando Servidores da API")
    return _deleter_instance.get_servers()

@st.cache_data(ttl=300)
def get_cached_server_channels(_deleter_instance, server_id):
    """Busca e armazena em cache os canais de um servidor específico"""
    print(f"CACHE MISS: Buscando Canais do Servidor {server_id} da API")
    return _deleter_instance.get_server_channels(server_id)

# --- FIM DAS FUNÇÕES DE CACHE ---


class DiscordMessageDeleterApp:
    def __init__(self):
        self.deleter = None
        self.authenticated = False
        self.user_info = None
        
    def get_avatar_url(self, user_id, avatar_hash, size=64):
        """Gera URL do avatar do usuário"""
        if avatar_hash:
            ext = 'gif' if avatar_hash.startswith('a_') else 'png'
            return f"https://cdn.discordapp.com/avatars/{user_id}/{avatar_hash}.{ext}?size={size}"
        return "https://cdn.discordapp.com/embed/avatars/0.png?size={size}"
    
    def get_dm_avatar_url(self, dm, size=64):
        """Gera URL do avatar para DM ou grupo"""
        if dm['type'] == 'group':
            avatar_hash = dm['avatar']
            if avatar_hash:
                return f"https://cdn.discordapp.com/channel-icons/{dm['id']}/{avatar_hash}.png?size={size}"
            return "https://cdn.discordapp.com/embed/avatars/0.png?size={size}"
        else:
            return self.get_avatar_url(dm['user_id'], dm['avatar'], size)
    
    def get_server_icon_url(self, server_id, icon_hash, size=64):
        """Gera URL do ícone do servidor"""
        if icon_hash:
            ext = 'gif' if icon_hash.startswith('a_') else 'png'
            return f"https://cdn.discordapp.com/icons/{server_id}/{icon_hash}.{ext}?size={size}"
        return "https://cdn.discordapp.com/embed/avatars/0.png?size={size}"
    
    def login_section(self):
        """Seção de login simplificada"""
        
        # --- INÍCIO DA MODIFICAÇÃO ---
        # Título principal da página de login
        st.markdown(
            '<div class="main-header"><i class="fa-brands fa-discord"></i> Discord Message Cleaner 🗑️</div>', 
            unsafe_allow_html=True
        )
        # --- FIM DA MODIFICAÇÃO ---
        
        col1, col2, col3 = st.columns([1, 2, 1])
        
        with col2:
            st.markdown("""
            <div class="login-box">
                <h3 style="text-align: center; color: #5865F2;">🔐 Login no Discord</h3>
                <p style="text-align: center;color: #5865F2;">Digite suas credenciais do Discord para continuar</p>
            </div>
            """, unsafe_allow_html=True)
            
            with st.form("login_form"):
                email = st.text_input("📧 Email", placeholder="seu.email@exemplo.com")
                password = st.text_input("🔒 Senha", type="password", placeholder="Sua senha do Discord")
                
                # --- INÍCIO DA MODIFICAÇÃO (2FA) ---
                has_2fa = st.checkbox("🔐 Tem 2FA (Segurança em Duas Etapas)?", help="Marque se sua conta tem 2FA. O navegador abrirá para você digitar o código.")
                # --- FIM DA MODIFICAÇÃO (2FA) ---

                login_button = st.form_submit_button("🚀 Fazer Login", use_container_width=True)
                
                if login_button:
                    if not email or not password:
                        st.error("❌ Por favor, preencha email e senha")
                        return
                    
                    # Mensagem personalizada baseada no 2FA
                    spinner_msg = "🔄 Conectando... Aguarde o navegador abrir para você completar o 2FA!" if has_2fa else "🔄 Conectando ao Discord... Isso pode levar alguns segundos"
                    
                    with st.spinner(spinner_msg):
                        try:
                            self.deleter = DiscordMessageDeleter()
                            # Passa o parametro has_2fa
                            result = self.deleter.login(email, password, has_2fa=has_2fa)
                            
                            if result:
                                self.authenticated = True
                                self.user_info = self.deleter.get_user_info()
                                st.session_state.authenticated = True
                                st.session_state.user_info = self.user_info
                                st.session_state.deleter = self.deleter
                                st.success("✅ Login realizado com sucesso!")
                                time.sleep(1)
                                st.rerun()
                            else:
                                st.error("❌ Falha no login. Verifique suas credenciais e tente novamente.")
                                # Limpa o deleter em caso de falha
                                if self.deleter:
                                    self.deleter.cleanup()
                                    self.deleter = None
                                
                        except Exception as e:
                            st.error(f"❌ Erro durante o login: {str(e)}")
                            if self.deleter:
                                self.deleter.cleanup()
                                self.deleter = None
    
    def dashboard_section(self):
        """Dashboard principal após login"""
        st.sidebar.title("🎮 Navegação")
        page = st.sidebar.radio("Ir para:", ["📊 Dashboard", "💬 Gerenciar DMs", "🏠 Gerenciar Servidores", "⚙️ Configurar Limpeza"])
        
        # Header do usuário com botão de doação no canto superior direito
        col1, col2, col3 = st.columns([1, 2, 1])
        
        with col1:
            pass  # Coluna vazia
        
        with col2:
            if self.user_info:
                avatar_url = self.get_avatar_url(
                    self.user_info['id'], 
                    self.user_info.get('avatar')
                )
                
                if avatar_url:
                    st.image(avatar_url, width=80)
                else:
                    st.markdown("👤")
                
                st.markdown(f"### 👋 Olá, {self.user_info.get('global_name', self.user_info.get('username', 'Usuário'))}!")
                st.caption(f"@{self.user_info.get('username', '')}")
        
        with col3:
            import streamlit.components.v1 as components
            
            # Botão de Doação
            if 'donation_open' not in st.session_state:
                st.session_state.donation_open = False

            if st.button("💝 Apoiar", key="donation_button", help="Fazer uma doação via PIX"):
                st.session_state.donation_open = not st.session_state.donation_open

            if st.session_state.donation_open:
                # QR Code
                st.image("img/qrcode.webp", width=200)
                
                # Chave PIX
                pix_code = "00020101021126580014br.gov.bcb.pix01360511689b-a234-41c0-9162-b6a2b8e32df05204000053039865802BR5920MATHEUS M SCHUMACHER6005IVOTI62070503***6304E316"
                
                st.markdown("**Chave PIX:**")
                
                # Usando components.html para copiar via JavaScript com visual profissional
                components.html(
                    f"""
                    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.2/css/all.min.css">
                    
                    <style>
                        .pix-container {{
                            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                            border-radius: 15px;
                            padding: 20px;
                            box-shadow: 0 4px 15px rgba(0,0,0,0.2);
                            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
                        }}
                        .pix-input {{
                            width: 100%;
                            padding: 12px;
                            border: 2px solid #e0e0e0;
                            border-radius: 8px;
                            font-size: 11px;
                            background: white;
                            margin-bottom: 15px;
                            box-sizing: border-box;
                            font-family: monospace;
                        }}
                        .copy-btn {{
                            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                            color: white;
                            border: 2px solid #000000;
                            padding: 14px 24px;
                            border-radius: 8px;
                            cursor: pointer;
                            width: 100%;
                            font-size: 16px;
                            font-weight: bold;
                            transition: all 0.3s ease;
                            box-shadow: 0 4px 10px rgba(102, 126, 234, 0.4);
                        }}
                        .copy-btn:hover {{
                            transform: translateY(-2px);
                            box-shadow: 0 6px 15px rgba(102, 126, 234, 0.6);
                        }}
                        .copy-btn:active {{
                            transform: translateY(0);
                        }}
                        .feedback {{
                            margin-top: 15px;
                            padding: 10px;
                            border-radius: 8px;
                            text-align: center;
                            font-weight: bold;
                            font-size: 14px;
                            background: #d4edda;
                            color: #155724;
                            border: 1px solid #c3e6cb;
                            display: none;
                        }}
                        .feedback.show {{
                            display: block;
                            animation: fadeIn 0.3s ease;
                        }}
                        @keyframes fadeIn {{
                            from {{ opacity: 0; transform: translateY(-10px); }}
                            to {{ opacity: 1; transform: translateY(0); }}
                        }}
                    </style>
                    
                    <div class="pix-container">
                        <input type="text" value="{pix_code}" id="pixInput" class="pix-input" readonly>
                        <button onclick="copyPix()" class="copy-btn">
                            <i class="fa-brands fa-pix"></i> Copiar Chave PIX
                        </button>
                        <div id="feedback" class="feedback">✅ Chave PIX copiada com sucesso!</div>
                    </div>
                    
                    <script>
                    function copyPix() {{
                        var input = document.getElementById("pixInput");
                        input.select();
                        input.setSelectionRange(0, 99999);
                        document.execCommand("copy");
                        
                        var feedback = document.getElementById("feedback");
                        feedback.classList.add("show");
                        
                        setTimeout(function() {{
                            feedback.classList.remove("show");
                        }}, 3000);
                    }}
                    </script>
                    """,
                    height=220,
                )
                
                # Botão para fechar
                if st.button("✖️ Fechar", use_container_width=True, type="secondary"):
                    st.session_state.donation_open = False
                    st.rerun()
        # Logout button
        if st.sidebar.button("🚪 Sair", use_container_width=True):
            if hasattr(st.session_state, 'deleter'):
                st.session_state.deleter.cleanup()
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            # Limpa o cache ao sair
            st.cache_data.clear()
            st.rerun()
        
        if page == "📊 Dashboard":
            self.show_dashboard()
        elif page == "💬 Gerenciar DMs":
            self.manage_dms()
        elif page == "🏠 Gerenciar Servidores":
            self.manage_servers()
        elif page == "⚙️ Configurar Limpeza":
            self.configure_cleanup()
    
    def show_dashboard(self):
        """Mostra dashboard com estatísticas"""
        st.header("📊 Dashboard")
        
        # Carregar dados (agora do cache)
        with st.spinner("🔄 Carregando dados..."):
            # --- MODIFICAÇÃO (CACHE) ---
            dms = get_cached_dms(self.deleter)
            servers = get_cached_servers(self.deleter)
            # --- FIM DA MODIFICAÇÃO ---
            
            # Estatísticas
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.markdown(f"""
                <div class="stats-card">
                    <h3>💬 DMs</h3>
                    <h2>{len(dms)}</h2>
                </div>
                """, unsafe_allow_html=True)
            
            with col2:
                st.markdown(f"""
                <div class="stats-card">
                    <h3>🏠 Servidores</h3>
                    <h2>{len(servers)}</h2>
                </div>
                """, unsafe_allow_html=True)
            
            with col3:
                st.markdown(f"""
                <div class="stats-card">
                    <h3>📂 Canais</h3>
                    <h2>N/A</h2>
                </div>
                """, unsafe_allow_html=True)
            
            with col4:
                status = "Conectado" if self.deleter.token else "Desconectado"
                st.markdown(f"""
                <div class="stats-card">
                    <h3>👤 Status</h3>
                    <h4>{status}</h4>
                </div>
                """, unsafe_allow_html=True)
        
        # Ações rápidas
        st.subheader("🚀 Ações Rápidas")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            # --- MODIFICAÇÃO (CACHE) ---
            if st.button("🔄 Atualizar Dados", use_container_width=True):
                st.cache_data.clear() # Limpa todo o cache de dados
                st.rerun() # Re-executa a página para buscar novos dados
            # --- FIM DA MODIFICAÇÃO ---
        
        with col2:
            if st.button("📋 Ver Todas as DMs", use_container_width=True):
                st.session_state.current_page = "💬 Gerenciar DMs"
                st.rerun()
        
        with col3:
            if st.button("🏠 Ver Todos os Servidores", use_container_width=True):
                st.session_state.current_page = "🏠 Gerenciar Servidores"
                st.rerun()
        
        # Últimas DMs
        st.subheader("💬 DMs Recentes")
        if dms:
            for dm in dms[:5]:
                with st.container():
                    col1, col2 = st.columns([1, 4])
                    with col1:
                        avatar_url = self.get_dm_avatar_url(dm)
                        st.image(avatar_url, width=40)
                    with col2:
                        st.write(f"**{dm['name']}**")
                        st.caption(f"@{dm['username']}")
                    st.divider()
        else:
            st.info("💬 Nenhuma DM encontrada.")
        
        # Servidores recentes
        st.subheader("🏠 Servidores Recentes")
        if servers:
            for server in servers[:5]:
                with st.container():
                    col1, col2 = st.columns([1, 4])
                    with col1:
                        icon_url = self.get_server_icon_url(server['id'], server.get('icon'))
                        st.image(icon_url, width=40)
                    with col2:
                        owner_flag = " 👑" if server.get('owner') else ""
                        st.write(f"**{server['name']}**{owner_flag}")
                        st.caption(f"ID: {server['id'][:8]}...")
                    st.divider()
        else:
            st.info("🏠 Nenhum servidor encontrado.")
    
    def manage_dms(self):
        """Gerenciamento de DMs"""
        st.header("💬 Gerenciar Mensagens Diretas (DMs)")
        
        # --- MODIFIFCAÇÃO (CACHE) ---
        with st.spinner("🔄 Carregando DMs..."):
            dms = get_cached_dms(self.deleter)
        # --- FIM DA MODIFICAÇÃO ---
        
        if not dms:
            st.info("💬 Nenhuma DM encontrada.")
            return
        
        # Garantir chaves necessárias na session_state
        if "dm_select_all_checkbox" not in st.session_state:
            st.session_state["dm_select_all_checkbox"] = False
        
        # Callback quando o "Selecionar Todos" das DMs muda
        def _dm_select_all_changed(dms_list):
            if st.session_state.get("dm_select_all_checkbox", False):
                for idx, dm in enumerate(dms_list):
                    try:
                        key = f"dm_select_{idx}"
                        if key not in st.session_state:
                            st.session_state[key] = False
                        st.session_state[key] = True
                    except Exception:
                        continue
        
        # Callback quando um item individual muda (desmarca o select_all)
        def _dm_item_changed(idx):
            key = f"dm_select_{idx}"
            if not st.session_state.get(key, False):
                st.session_state["dm_select_all_checkbox"] = False
        
        # Callback para o botão "Desmarcar"
        def _dm_deselect_all_clicked(dms_list):
            st.session_state["dm_select_all_checkbox"] = False
            for idx in range(len(dms_list)):
                key = f"dm_select_{idx}"
                if key in st.session_state:
                    st.session_state[key] = False
        
        # Filtros e seleção em massa
        col1, col2 = st.columns([3, 1])
        
        with col1:
            search_term = st.text_input("🔍 Buscar DM por nome:", placeholder="Digite para filtrar...")
        
        with col2:
            btn_col1, btn_col2 = st.columns(2)
            with btn_col1:
                st.checkbox(
                    "Selecionar Todos",
                    key="dm_select_all_checkbox",
                    on_change=_dm_select_all_changed,
                    args=(dms,)
                )
            with btn_col2:
                # Botão "Desmarcar Todos" agora usa on_click
                st.button(
                    "Desmarcar",
                    key="dm_deselect_all_button",
                    help="Desmarcar todas as DMs",
                    on_click=_dm_deselect_all_clicked,
                    args=(dms,)
                )
        
        # Lista de DMs
        st.subheader(f"📋 Lista de DMs ({len(dms)})")
        
        selected_dms = []
        
        for i, dm in enumerate(dms):
            # Filtro de busca com handling
            try:
                if search_term and search_term.lower() not in dm['name'].lower() and search_term.lower() not in dm.get('username', '').lower():
                    continue
            except (TypeError, AttributeError):
                continue
            
            with st.container():
                col1, col2, col3, col4 = st.columns([1, 5, 1, 1])
                
                with col1:
                    avatar_url = self.get_dm_avatar_url(dm)
                    st.image(avatar_url, width=40)
                
                with col2:
                    st.write(f"**{dm['name']}**")
                    caption = f"@{dm['username']} • ID: {dm['id'][:8]}..."
                    if dm['type'] == 'group':
                        caption += " (Grupo)"
                    st.caption(caption)
                
                with col3:
                    key = f"dm_select_{i}"
                    if key not in st.session_state:
                        st.session_state[key] = False
                    
                    selected = st.checkbox("Selecionar", key=key, on_change=_dm_item_changed, args=(i,), label_visibility="visible")
                    
                    if selected:
                        selected_dms.append(dm)
                
                with col4:
                    if st.button("🗑️", key=f"dm_quick_delete_{i}", help="Deletar todas as mensagens nesta DM"):
                        self.quick_delete([dm], "DMs")
                
                st.divider()
        
        # Ações para DMs selecionadas
        if selected_dms:
            st.subheader(f"🎯 {len(selected_dms)} DMs Selecionadas")
            
            with st.expander("📋 Ver DMs Selecionadas"):
                for dm in selected_dms:
                    st.write(f"• {dm['name']} (@{dm['username']})")
            
            self.cleanup_configuration_section(selected_dms, "DMs")
    
    def manage_servers(self):
        """Gerenciamento de servidores e canais"""
        st.header("🏠 Gerenciar Servidores e Canais")
        
        # --- MODIFICAÇÃO (CACHE) ---
        with st.spinner("🔄 Carregando servidores..."):
            servers = get_cached_servers(self.deleter)
        # --- FIM DA MODIFICAÇÃO ---
        
        if not servers:
            st.info("🏠 Nenhum servidor encontrado.")
            return
        
        if 'expanded_servers' not in st.session_state:
            st.session_state.expanded_servers = {}
        
        search_term = st.text_input("🔍 Buscar servidor por nome:", placeholder="Digite para filtrar...")
        
        st.subheader(f"📋 Lista de Servidores ({len(servers)})")
        
        all_selected_channels = []
        
        for i, server in enumerate(servers):
            try:
                if search_term and search_term.lower() not in server['name'].lower():
                    continue
            except (TypeError, AttributeError):
                continue
            
            with st.container():
                col1, col2, col3, col4, col5 = st.columns([1, 4, 1, 1, 1])
                
                with col1:
                    icon_url = self.get_server_icon_url(server['id'], server.get('icon'))
                    st.image(icon_url, width=40)
                
                with col2:
                    owner_flag = " 👑" if server.get('owner') else ""
                    st.write(f"**{server['name']}**{owner_flag}")
                    st.caption(f"ID: {server['id'][:8]}...")
                
                with col3:
                    server_select_key = f"server_select_{i}"
                    if server_select_key not in st.session_state:
                        st.session_state[server_select_key] = False
                    
                    selected = st.checkbox("", key=server_select_key, label_visibility="collapsed")
                
                with col4:
                    server_key = f"server_{server['id']}"
                    is_expanded = st.session_state.expanded_servers.get(server_key, False)
                    
                    if selected:
                        if st.button("🔽" if not is_expanded else "🔼", key=f"expand_{i}", help="Expandir/Minimizar canais"):
                            st.session_state.expanded_servers[server_key] = not is_expanded
                            st.rerun()
                    else:
                        st.button("⚫", key=f"expand_disabled_{i}", disabled=True, help="Selecione o servidor primeiro")
                
                with col5:
                    if st.button("🗑️", key=f"server_quick_delete_{i}", help="Deletar mensagens dos canais selecionados"):
                        selected_for_server = [ch for ch in all_selected_channels if ch.get('server_id') == server['id']]
                        if selected_for_server:
                            self.quick_delete(selected_for_server, "canais")
                        else:
                            st.warning("⚠️ Nenhum canal selecionado neste servidor.")
                
                if selected and st.session_state.expanded_servers.get(server_key, False):
                    # --- MODIFICAÇÃO (CACHE) ---
                    channels = get_cached_server_channels(self.deleter, server['id'])
                    # --- FIM DA MODIFICAÇÃO ---
                    
                    if channels:
                        select_all_key = f"select_all_server_{i}"
                        if select_all_key not in st.session_state:
                            st.session_state[select_all_key] = False
                        
                        def _server_select_all_changed(si, chs):
                            widget_key = f"select_all_server_{si}"
                            if st.session_state.get(widget_key, False):
                                for jj in range(len(chs)):
                                    k = f"ch_{si}_{jj}"
                                    if k not in st.session_state:
                                        st.session_state[k] = False
                                    st.session_state[k] = True
                        
                        def _server_channel_item_changed(si, cj):
                            k = f"ch_{si}_{cj}"
                            if not st.session_state.get(k, False):
                                parent_widget = f"select_all_server_{si}"
                                st.session_state[parent_widget] = False
                        
                        def _server_deselect_all_clicked(server_idx, chs, key_to_deselect):
                            st.session_state[key_to_deselect] = False
                            for jj in range(len(chs)):
                                k = f"ch_{server_idx}_{jj}"
                                if k in st.session_state:
                                    st.session_state[k] = False
                        
                        ch_btn_col1, ch_btn_col2 = st.columns(2)
                        
                        with ch_btn_col1:
                            st.checkbox(f"✅ Selecionar todos ({len(channels)} canais)", key=select_all_key, on_change=_server_select_all_changed, args=(i, channels))
                        
                        with ch_btn_col2:
                            st.button(
                                "Desmarcar",
                                key=f"server_deselect_all_{i}",
                                help="Desmarcar todos os canais deste servidor",
                                on_click=_server_deselect_all_clicked,
                                args=(i, channels, select_all_key)
                            )
                        
                        st.markdown(f"<div class='channel-list'>", unsafe_allow_html=True)
                        
                        for j, channel in enumerate(channels):
                            with st.container():
                                col_ch1, col_ch2, col_ch3 = st.columns([5, 1, 1])
                                
                                with col_ch1:
                                    channel_type = "📢" if channel.get('type') == 5 else "💬"
                                    st.markdown(f"<small>{channel_type} <b>#{channel['name']}</b></small>", unsafe_allow_html=True)
                                
                                with col_ch2:
                                    ch_key = f"ch_{i}_{j}"
                                    if ch_key not in st.session_state:
                                        st.session_state[ch_key] = False
                                    
                                    ch_selected = st.checkbox("", key=ch_key, label_visibility="collapsed", on_change=_server_channel_item_changed, args=(i, j))
                                    
                                    if ch_selected:
                                        channel_with_server = channel.copy()
                                        channel_with_server['server_name'] = server['name']
                                        channel_with_server['server_id'] = server['id']
                                        all_selected_channels.append(channel_with_server)
                                
                                with col_ch3:
                                    if st.button("🗑️", key=f"ch_del_{i}_{j}", help="Deletar mensagens deste canal"):
                                        channel_with_server = channel.copy()
                                        channel_with_server['server_name'] = server['name']
                                        channel_with_server['server_id'] = server['id']
                                        self.quick_delete([channel_with_server], "canais")
                        
                        st.markdown("</div>", unsafe_allow_html=True)
                        
                    else:
                        st.caption(" 📂 Nenhum canal de texto encontrado")
                
                st.markdown("<div style='margin-bottom: 8px;'></div>", unsafe_allow_html=True)
        
        if all_selected_channels:
            st.markdown("---")
            st.subheader(f"🎯 {len(all_selected_channels)} Canais Selecionados no Total")
            
            with st.expander("📋 Ver Todos os Canais Selecionados"):
                for channel in all_selected_channels:
                    channel_type = "📢" if channel.get('type') == 5 else "💬"
                    st.write(f"• {channel_type} #{channel['name']} (📍 {channel['server_name']})")
            
            self.cleanup_configuration_section(all_selected_channels, "canais")
    
    def quick_delete(self, channels, channel_type):
        """Executa deleção rápida com configurações padrão SEGURAS"""
        cleanup_option = "🗑️ Todas as mensagens"
        # CORREÇÃO: Delays aumentados para evitar rate limits
        min_delay = 2.5
        max_delay = 4.5
        show_progress = True

        # --- MODIFICAÇÃO (CACHE) ---
        # Limpa todo o cache de dados para garantir que a lista seja atualizada
        # após a deleção.
        st.cache_data.clear() 
        # --- FIM DA MODIFICAÇÃO ---

        self.execute_cleanup(channels, cleanup_option, min_delay, max_delay, None, None, show_progress)
    
    def cleanup_configuration_section(self, channels, channel_type):
        """Seção de configuração de limpeza (reutilizável)"""
        st.subheader("⚙️ Configurar Limpeza")
        
        col1, col2 = st.columns(2)
        
        with col1:
            cleanup_option = st.radio(
                "Escolha o tipo de limpeza:",
                ["🗑️ Todas as mensagens", "📅 Mensagens dos últimos dias", "🔢 Últimas X mensagens"]
            )
        
        with col2:
            if cleanup_option == "📅 Mensagens dos últimos dias":
                days = st.number_input("Número de dias:", min_value=1, max_value=365, value=30)
            elif cleanup_option == "🔢 Últimas X mensagens":
                message_limit = st.number_input("Número de mensagens:", min_value=1, max_value=1000, value=100)
            else:
                days = None
                message_limit = None
        
        st.subheader("🛡️ Configurações de Segurança")
        col1, col2 = st.columns(2)
        
        with col1:
            # CORREÇÃO: Valores mínimos aumentados para evitar rate limit
            min_delay = st.slider("Delay mínimo entre exclusões (segundos):", 2.0, 6.0, 2.5, 0.5)
            max_delay = st.slider("Delay máximo entre exclusões (segundos):", 3.0, 12.0, 4.5, 0.5)
        
        with col2:
            show_progress = st.checkbox("📊 Mostrar progresso detalhado", value=True)
            st.info("💡 **Dica:** Delays maiores (4-6s) são mais seguros para evitar bloqueios.")
        
        if st.button(f"🚀 Executar Limpeza nos {channel_type} Selecionados", type="primary", use_container_width=True):
            # --- MODIFICAÇÃO (CACHE) ---
            # Limpa o cache relevante ANTES de executar a limpeza
            st.cache_data.clear()
            # --- FIM DA MODIFICAÇÃO ---

            self.execute_cleanup(
                channels, 
                cleanup_option, 
                min_delay, 
                max_delay,
                days,
                message_limit,
                show_progress
            )
    
    def configure_cleanup(self):
        """Configurações avançadas de limpeza"""
        st.header("⚙️ Configurações de Limpeza")
        
        st.subheader("🛡️ Configurações de Segurança")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.info("""
            **📊 Sobre Rate Limiting:**
            - Delays entre 1-3 segundos são geralmente seguros
            - Evite deletar mais de 100 mensagens por minuto
            - Pausas longas entre canais/servidores são recomendadas
            """)
        
        with col2:
            default_min_delay = st.number_input("Delay mínimo padrão (segundos):", 0.5, 5.0, 1.0, 0.1)
            if default_min_delay < 1.0:
                st.warning("⚠️ Aviso: Definir o delay mínimo abaixo de 1.0 segundo pode aumentar o risco de punição pelo Discord, como suspensão ou banimento da conta. Não nos responsabilizamos por qualquer consequência à sua conta, pois essa configuração deixa de ser segura. Recomendamos manter valores de 1.0 ou superiores para evitar problemas.")
            default_max_delay = st.number_input("Delay máximo padrão (segundos):", 1.0, 10.0, 3.0, 0.1)
            batch_size = st.number_input("Tamanho do lote de mensagens:", 10, 200, 50)
        
        st.subheader("🔧 Configurações Avançadas")
        
        advanced_col1, advanced_col2 = st.columns(2)
        
        with advanced_col1:
            auto_retry = st.checkbox("Tentar novamente em caso de falha", value=True)
            max_retries = st.number_input("Máximo de tentativas:", 1, 10, 3) if auto_retry else 1
            preserve_pinned = st.checkbox("Preservar mensagens fixadas", value=True)
        
        with advanced_col2:
            skip_old_messages = st.checkbox("Pular mensagens muito antigas (>1 ano)", value=False)
            log_operations = st.checkbox("Manter log das operações", value=True)
        
        if st.button("💾 Salvar Configurações", use_container_width=True):
            st.success("✅ Configurações salvas com sucesso!")
    
    def execute_cleanup(self, channels, cleanup_option, min_delay, max_delay, days=None, message_limit=None, show_progress=True):
        """Executa a limpeza de mensagens com progressos de Fetching e Deletion em tempo real e suporte a cancelamento seguro."""

        # CORREÇÃO: Proteção contra deleter None ou inválido
        if not self.deleter:
            st.error("❌ Erro: Sessão expirada. Por favor, faça login novamente.")
            if st.button("🔄 Ir para Login"):
                for key in list(st.session_state.keys()):
                    del st.session_state[key]
                st.rerun()
            return
        
        # Verifica se o loop async ainda está rodando
        if not self.deleter._loop_thread.is_alive():
            st.error("❌ Erro: Conexão perdida. Por favor, faça login novamente.")
            if st.button("🔄 Ir para Login"):
                for key in list(st.session_state.keys()):
                    del st.session_state[key]
                st.rerun()
            return

        # --- 1. CONFIGURAÇÃO DE UI E PREPARAÇÃO ---
        progress_bar = st.progress(0)
        status_container = st.empty()
        results_placeholder = st.empty()
        
        st.toast("💡 Processando em segundo plano. Clique no 'X' para interromper de forma segura.", icon="⏳")

        total_deleted = 0
        total_channels = len(channels)

        # Limpeza de flags e estatísticas
        self.deleter.reset_stats()
        # IMPORTANTE: Limpa o flag de cancelamento para que a nova execução possa começar
        self.deleter._stop_event.clear() 

        update_queue = queue.Queue()
        
        # Flag para rastrear se o usuário cancelou a operação
        was_cancelled_by_user = False
        
        # CORREÇÃO: Throttle para evitar sobrecarga de UI
        last_ui_update = [0.0]  # Lista mutável para closure
        UI_UPDATE_THROTTLE = 0.3  # Atualiza UI no máximo a cada 0.3 segundos

        # Função de callback para a fase de busca (fetch) COM THROTTLE
        def fetch_callback(user_message_count, channel_name):
            current_time = time.time()
            # Só enfileira se passou tempo suficiente desde última atualização
            if current_time - last_ui_update[0] >= UI_UPDATE_THROTTLE:
                last_ui_update[0] = current_time
                update_queue.put({"type": "fetch", "current": user_message_count, "name": channel_name})

        # Função de callback para a fase de exclusão (delete) COM THROTTLE
        def delete_callback(current, total, name):
            current_time = time.time()
            # Sempre envia a última mensagem OU se passou tempo suficiente
            if current == total or current_time - last_ui_update[0] >= UI_UPDATE_THROTTLE:
                last_ui_update[0] = current_time
                update_queue.put({"type": "delete", "current": current, "total": total, "name": name})

        # --- 2. EXECUÇÃO (BLOCO DE SEGURANÇA) ---
        try:
            with ThreadPoolExecutor(max_workers=1) as executor:
                
                for i, channel in enumerate(channels):
                    # Checagem de parada antes de iniciar o canal
                    if self.deleter._stop_event.is_set():
                        was_cancelled_by_user = True
                        break

                    channel_name = channel.get('name', channel.get('server_name', 'Canal'))
                    
                    # --- A. INICIAR BUSCA DE MENSAGENS (FETCHING) ---
                    
                    fetch_limit = message_limit if cleanup_option == "🔢 Últimas X mensagens" else None
                    
                    status_container.info(f"🔍 Preparando {channel_name}... (Iniciando busca {i+1}/{total_channels})")
                    progress_bar.progress(0.01) # Mostra que algo começou
                    
                    try:
                        # 1. Submete a busca para a thread pool (agora com fetch_callback)
                        if cleanup_option == "🗑️ Todas as mensagens":
                            fetch_future = executor.submit(
                                self.deleter.get_all_user_messages, channel, fetch_all=True, progress_callback=fetch_callback
                            )
                        elif cleanup_option == "📅 Mensagens dos últimos dias":
                            since_date = datetime.now() - timedelta(days=days)
                            fetch_future = executor.submit(
                                self.deleter.get_messages_since_date, channel, since_date, progress_callback=fetch_callback
                            )
                        elif cleanup_option == "🔢 Últimas X mensagens":
                            fetch_future = executor.submit(
                                self.deleter.get_user_messages, channel, limit=fetch_limit, progress_callback=fetch_callback
                            )
                        
                        # Loop para monitorar o progresso da busca
                        while not fetch_future.done():
                            if self.deleter._stop_event.is_set():
                                was_cancelled_by_user = True
                                break
                            try:
                                update = update_queue.get(timeout=0.1)
                                if update["type"] == "fetch" and show_progress:
                                    status_container.info(
                                        f"🔍 Buscando em {update['name']}: **{update['current']}** mensagens suas encontradas..."
                                    )
                                # Mantém a barra em 1% para mostrar atividade
                                progress_bar.progress(0.01) 
                            except queue.Empty:
                                pass
                        
                        # Pega o resultado da busca (timeout aumentado para deleções grandes)
                        messages = fetch_future.result(timeout=900)  # 15 min timeout para canais grandes
                        total_messages = len(messages)
                        
                        if not messages:
                            status_container.warning(f"ℹ️ Nenhuma mensagem encontrada em {channel_name}")
                            time.sleep(1)
                            continue

                        # --- B. INICIAR EXCLUSÃO DE MENSAGENS (DELETION) ---
                        
                        # Limpa o container antes de mudar de estado para evitar overlap
                        status_container.empty()
                        status_container.info(f"🗑️ **{total_messages}** mensagens prontas para exclusão em **{channel_name}**...")
                        
                        # 2. Inicia a deleção (agora usando delete_callback)
                        delete_future = executor.submit(
                            self.deleter.safe_delete_messages,
                            messages,
                            channel,
                            delay_range=(min_delay, max_delay),
                            progress_callback=delete_callback
                        )

                        # Loop de atualização da UI (focado na deleção)
                        while not delete_future.done():
                            if self.deleter._stop_event.is_set():
                                was_cancelled_by_user = True
                                break
                            try:
                                update = update_queue.get(timeout=0.1)
                                if update["type"] == "delete" and show_progress:
                                    current = update["current"]
                                    
                                    # Calcula porcentagem do canal atual
                                    pct_channel = min(current / total_messages, 1.0)
                                    
                                    status_container.markdown(f"""
                                        **Deletando em:** `{channel_name}`  
                                        🔄 Progresso: **{current}/{total_messages}**
                                    """)
                                    progress_bar.progress(pct_channel)
                                    
                            except queue.Empty:
                                pass
                        
                        # Pegar o resultado final da thread de deleção (timeout aumentado)
                        if not self.deleter._stop_event.is_set():
                            channel_deleted_count = delete_future.result(timeout=7200)  # 2 horas para canais muito grandes
                            total_deleted += channel_deleted_count
                            status_container.success(f"✅ {channel_deleted_count} mensagens deletadas de {channel_name}")
                            time.sleep(1)
                    
                    except Exception as e:
                        if not self.deleter._stop_event.is_set():
                            status_container.error(f"❌ Erro ao processar {channel_name}: {str(e)}")
                            time.sleep(2)

                    # Pausa entre canais para segurança
                    if i < total_channels - 1 and not self.deleter._stop_event.is_set():
                        status_container.info("⏳ Aguardando cooldown entre canais...")
                        time.sleep(2)

        # Captura interrupções do Streamlit (clique em "Stop" ou F5)
        except (KeyboardInterrupt, SystemExit):
            was_cancelled_by_user = True
        except asyncio.CancelledError:
            # CORREÇÃO: Trata cancelamento async como cancelamento pelo usuário
            was_cancelled_by_user = True
        except TimeoutError:
            status_container.error("⏱️ Timeout: A operação demorou demais para responder.")
        except Exception as e:
            # Log para debug, mas não interrompe limpeza
            error_msg = str(e)
            if "cancelada" not in error_msg.lower() and "cancelled" not in error_msg.lower():
                print(f"⚠️ Erro durante execução: {e}") 
            else:
                was_cancelled_by_user = True 
        
        # --- 3. LIMPEZA E RELATÓRIO (BLOCO FINALLY) ---
        finally:
            # NÃO definir stop_event aqui - só é definido quando o usuário cancela
            # O stop_event é gerenciado pelo próprio fluxo ou pelo usuário

            # Limpa a área de progresso e mostra o relatório final
            progress_bar.empty()
            status_container.empty()
            
            with results_placeholder.container():
                st.markdown("---")
                # Verifica se o processo foi cancelado pelo usuário
                if was_cancelled_by_user:
                    st.warning("🛑 Operação cancelada pelo usuário.")
                else:
                    st.success(f"🎉 Limpeza concluída! Total de mensagens deletadas: **{total_deleted}**")
                    if total_deleted > 0: st.balloons()
                
                stats = self.deleter.get_stats()
                col1, col2, col3, col4 = st.columns(4)
                
                col1.metric("Canais Processados", total_channels)
                col2.metric("Mensagens Deletadas", stats['deleted_count'])
                col3.metric("Falhas", stats['failed_count'])
                col4.metric("Rate Limits", stats['throttled_count'])
                
                if st.button("🔄 Recarregar Dados"):
                    st.cache_data.clear()
                    st.rerun()
    
    def run(self):
        """Executa a aplicação principal"""
        if 'authenticated' not in st.session_state:
            st.session_state.authenticated = False
        
        if st.session_state.authenticated:
            self.authenticated = True
            self.user_info = st.session_state.get('user_info')
            self.deleter = st.session_state.get('deleter')
            self.dashboard_section()
        else:
            self.login_section()

# Executar a aplicação
if __name__ == "__main__":
    try:
        app = DiscordMessageDeleterApp()
        app.run()
    except Exception as e:
        # CORREÇÃO: Não reseta login automaticamente - apenas mostra erro
        st.error("❌ Ocorreu um erro na aplicação.")
        st.error(f"Detalhes: {str(e)}")
        # Log do erro no console para debug
        traceback.print_exc()
        
        # CORREÇÃO: Mostra opção de retry em vez de forçar logout
        st.warning("⚠️ Se o problema persistir, clique no botão abaixo para reiniciar.")
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("🔄 Tentar Novamente", use_container_width=True):
                st.rerun()
        with col2:
            if st.button("🚪 Fazer Logout", use_container_width=True):
                # Só faz logout se o usuário clicar explicitamente
                if 'deleter' in st.session_state and st.session_state.deleter:
                    try:
                        st.session_state.deleter.cleanup()
                    except Exception:
                        pass
                for key in list(st.session_state.keys()):
                    del st.session_state[key]
                st.cache_data.clear()
                st.rerun()