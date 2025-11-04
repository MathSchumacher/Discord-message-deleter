# app.py
import streamlit as st
import pandas as pd
import time
import random
from datetime import datetime, timedelta
import sys
import os
import asyncio
from message_deleter import DiscordMessageDeleter
import base64
import requests
from io import BytesIO
from PIL import Image

# Configuração da página
st.set_page_config(
    page_title="Discord Message Cleaner",
    page_icon="🗑️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# CSS customizado
st.markdown("""
<style>
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
</style>
""", unsafe_allow_html=True)

class DiscordMessageDeleterApp:
    def __init__(self):
        self.deleter = None
        self.authenticated = False
        self.user_info = None
        
    def get_avatar_url(self, user_id, avatar_hash, size=64):
        """Gera URL do avatar"""
        if avatar_hash:
            ext = 'gif' if avatar_hash.startswith('a_') else 'png'
            return f"https://cdn.discordapp.com/avatars/{user_id}/{avatar_hash}.{ext}?size={size}"
        return "https://cdn.discordapp.com/embed/avatars/0.png?size={size}"
    
    def get_server_icon_url(self, server_id, icon_hash, size=64):
        """Gera URL do ícone do servidor"""
        if icon_hash:
            ext = 'gif' if icon_hash.startswith('a_') else 'png'
            return f"https://cdn.discordapp.com/icons/{server_id}/{icon_hash}.{ext}?size={size}"
        return "https://cdn.discordapp.com/embed/avatars/0.png?size={size}"
    
    def login_section(self):
        """Seção de login simplificada"""
        st.markdown('<div class="main-header">🗑️ Discord Message Cleaner</div>', unsafe_allow_html=True)
        
        col1, col2, col3 = st.columns([1, 2, 1])
        
        with col2:
            st.markdown("""
            <div class="login-box">
                <h3 style="text-align: center; color: #5865F2;">🔐 Login no Discord</h3>
                <p style="text-align: center;">Digite suas credenciais do Discord para continuar</p>
            </div>
            """, unsafe_allow_html=True)
            
            with st.form("login_form"):
                email = st.text_input("📧 Email", placeholder="seu.email@exemplo.com")
                password = st.text_input("🔒 Senha", type="password", placeholder="Sua senha do Discord")
                
                login_button = st.form_submit_button("🚀 Fazer Login", use_container_width=True)
                
                if login_button:
                    if not email or not password:
                        st.error("❌ Por favor, preencha email e senha")
                        return
                    
                    with st.spinner("🔄 Conectando ao Discord... Isso pode levar alguns segundos"):
                        try:
                            self.deleter = DiscordMessageDeleter()
                            result = self.deleter.login(email, password)
                            
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
        
        # Header do usuário
        col1, col2, col3 = st.columns([1, 2, 1])
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
        
        # Logout button
        if st.sidebar.button("🚪 Sair", use_container_width=True):
            if hasattr(st.session_state, 'deleter'):
                st.session_state.deleter.cleanup()
            for key in list(st.session_state.keys()):
                del st.session_state[key]
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
        
        # Carregar dados
        with st.spinner("🔄 Carregando dados..."):
            dms = self.deleter.get_dms()
            servers = self.deleter.get_servers()
            
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
                # Comentado para evitar muitas chamadas API e rate limits
                # total_channels = len(dms)
                # for server in servers:
                #     channels = self.deleter.get_server_channels(server['id'])
                #     total_channels += len(channels)
                #     time.sleep(0.5)  # Delay para evitar rate limit
                
                # st.markdown(f"""
                # <div class="stats-card">
                #     <h3>📂 Canais</h3>
                #     <h2>{total_channels}</h2>
                # </div>
                # """, unsafe_allow_html=True)
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
            if st.button("🔄 Atualizar Dados", use_container_width=True):
                st.rerun()
        
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
                        avatar_url = self.get_avatar_url(dm.get('id'), dm.get('avatar'))
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
        
        with st.spinner("🔄 Carregando DMs..."):
            dms = self.deleter.get_dms()
        
        if not dms:
            st.info("💬 Nenhuma DM encontrada.")
            return
        
        # Filtros e seleção em massa
        col1, col2 = st.columns([3, 1])
        
        with col1:
            search_term = st.text_input("🔍 Buscar DM por nome:", placeholder="Digite para filtrar...")
        
        with col2:
            select_all = st.checkbox("Selecionar Todos")
        
        # Lista de DMs
        st.subheader(f"📋 Lista de DMs ({len(dms)})")
        
        selected_dms = []
        
        for i, dm in enumerate(dms):
            # Filtro de busca
            if search_term and search_term.lower() not in dm['name'].lower() and search_term.lower() not in dm['username'].lower():
                continue
            
            with st.container():
                col1, col2, col3, col4 = st.columns([1, 5, 1, 1])
                
                with col1:
                    avatar_url = self.get_avatar_url(dm.get('id'), dm.get('avatar'))
                    st.image(avatar_url, width=40)
                
                with col2:
                    st.write(f"**{dm['name']}**")
                    st.caption(f"@{dm['username']} • ID: {dm['id'][:8]}...")
                
                with col3:
                    selected = st.checkbox("Selecionar", key=f"dm_select_{i}", value=select_all)
                    if selected:
                        selected_dms.append(dm)
                
                with col4:
                    if st.button("🗑️", key=f"dm_quick_delete_{i}", help="Deletar todas as mensagens nesta DM"):
                        if st.session_state.get(f"confirm_dm_{i}", False):
                            self.quick_delete([dm], "DMs")
                            st.session_state[f"confirm_dm_{i}"] = False
                        else:
                            st.warning("Confirme para deletar todas as mensagens nesta DM.")
                            st.session_state[f"confirm_dm_{i}"] = True
                
                st.divider()
        
        # Ações para DMs selecionadas
        if selected_dms:
            st.subheader(f"🎯 {len(selected_dms)} DMs Selecionadas")
            
            # Preview das selecionadas
            with st.expander("📋 Ver DMs Selecionadas"):
                for dm in selected_dms:
                    st.write(f"• {dm['name']} (@{dm['username']})")
            
            # Configuração da limpeza
            self.cleanup_configuration_section(selected_dms, "DMs")
    
    def manage_servers(self):
        """Gerenciamento de servidores e canais"""
        st.header("🏠 Gerenciar Servidores e Canais")
        
        with st.spinner("🔄 Carregando servidores..."):
            servers = self.deleter.get_servers()
        
        if not servers:
            st.info("🏠 Nenhum servidor encontrado.")
            return
        
        # Filtro para servidores
        search_term = st.text_input("🔍 Buscar servidor por nome:", placeholder="Digite para filtrar...")
        
        # Lista de servidores
        st.subheader(f"📋 Lista de Servidores ({len(servers)})")
        
        selected_servers = []
        
        for i, server in enumerate(servers):
            if search_term and search_term.lower() not in server['name'].lower():
                continue
            
            with st.container():
                col1, col2, col3, col4 = st.columns([1, 5, 1, 1])
                
                with col1:
                    icon_url = self.get_server_icon_url(server['id'], server.get('icon'))
                    st.image(icon_url, width=40)
                
                with col2:
                    owner_flag = " 👑" if server.get('owner') else ""
                    st.write(f"**{server['name']}**{owner_flag}")
                    st.caption(f"ID: {server['id'][:8]}...")
                
                with col3:
                    selected = st.checkbox("Selecionar", key=f"server_select_{i}")
                    if selected:
                        selected_servers.append(server)
                
                with col4:
                    if st.button("🗑️", key=f"server_quick_delete_{i}", help="Deletar todas as mensagens em todos os canais deste servidor"):
                        if st.session_state.get(f"confirm_server_{i}", False):
                            channels = self.deleter.get_server_channels(server['id'])
                            channels_with_server = [ch.copy() for ch in channels]
                            for ch in channels_with_server:
                                ch['server_name'] = server['name']
                                ch['server_id'] = server['id']
                            self.quick_delete(channels_with_server, "canais")
                            st.session_state[f"confirm_server_{i}"] = False
                        else:
                            st.warning("Confirme para deletar todas as mensagens neste servidor.")
                            st.session_state[f"confirm_server_{i}"] = True
                
                st.divider()
        
        # Para servidores selecionados, mostrar canais
        if selected_servers:
            for server in selected_servers:
                st.subheader(f"📂 Canais em {server['name']}")
                
                channels = self.deleter.get_server_channels(server['id'])
                
                if not channels:
                    st.info(f"📂 Nenhum canal encontrado em {server['name']}.")
                    continue
                
                select_all_channels = st.checkbox(f"Selecionar Todos os Canais em {server['name']}")
                
                selected_channels = []
                
                for j, channel in enumerate(channels):
                    with st.container():
                        col1, col2 = st.columns([6, 1])
                        
                        with col1:
                            channel_type = "📢" if channel.get('type') == 5 else "💬"
                            st.write(f"{channel_type} **#{channel['name']}**")
                            if channel.get('topic'):
                                st.caption(f"Tópico: {channel['topic'][:100]}...")
                            else:
                                st.caption(f"ID: {channel['id'][:8]}...")
                        
                        with col2:
                            selected = st.checkbox("Selecionar", key=f"channel_{i}_{j}", value=select_all_channels)
                            if selected:
                                channel_with_server = channel.copy()
                                channel_with_server['server_name'] = server['name']
                                channel_with_server['server_id'] = server['id']
                                selected_channels.append(channel_with_server)
                        
                        st.divider()
                
                if selected_channels:
                    st.subheader(f"🎯 {len(selected_channels)} Canais Selecionados em {server['name']}")
                    
                    with st.expander("📋 Ver Canais Selecionados"):
                        for channel in selected_channels:
                            channel_type = "📢" if channel.get('type') == 5 else "💬"
                            st.write(f"• {channel_type} #{channel['name']} (em {channel['server_name']})")
                    
                    self.cleanup_configuration_section(selected_channels, "canais")
    
    def quick_delete(self, channels, channel_type):
        """Executa deleção rápida com configurações padrão"""
        cleanup_option = "🗑️ Todas as mensagens"
        min_delay = 1.0
        max_delay = 3.0
        show_progress = True
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
        
        # Configurações de segurança
        st.subheader("🛡️ Configurações de Segurança")
        col1, col2 = st.columns(2)
        
        with col1:
            min_delay = st.slider("Delay mínimo entre exclusões (segundos):", 0.5, 5.0, 1.0, 0.5)
            max_delay = st.slider("Delay máximo entre exclusões (segundos):", 1.0, 10.0, 3.0, 0.5)
        
        with col2:
            confirm_deletion = st.checkbox("✅ Confirmar antes de excluir", value=True)
            show_progress = st.checkbox("📊 Mostrar progresso detalhado", value=True)
        
        # Botão de execução
        if st.button(f"🚀 Executar Limpeza nos {channel_type} Selecionados", type="primary", use_container_width=True):
            if confirm_deletion:
                st.warning(f"⚠️ Você está prestes a deletar mensagens de {len(channels)} {channel_type}. Esta ação é irreversível!")
                
                col1, col2, col3 = st.columns([1, 2, 1])
                with col2:
                    if st.button("🔴 CONFIRMAR EXCLUSÃO", type="secondary", use_container_width=True):
                        self.execute_cleanup(
                            channels, 
                            cleanup_option, 
                            min_delay, 
                            max_delay,
                            days,
                            message_limit,
                            show_progress
                        )
            else:
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
        """Executa a limpeza de mensagens"""
        progress_bar = st.progress(0)
        status_text = st.empty()
        results_placeholder = st.empty()
        
        total_deleted = 0
        total_channels = len(channels)
        
        for i, channel in enumerate(channels):
            channel_name = channel.get('name', channel.get('server_name', 'Canal'))
            status_text.text(f"🔍 Processando {channel_name}... ({i+1}/{total_channels})")
            
            try:
                # Obter mensagens baseado na opção selecionada
                messages = []
                
                if cleanup_option == "🗑️ Todas as mensagens":
                    messages = self.deleter.get_all_user_messages(channel)
                
                elif cleanup_option == "📅 Mensagens dos últimos dias":
                    since_date = datetime.now() - timedelta(days=days)
                    messages = self.deleter.get_messages_since_date(channel, since_date)
                
                elif cleanup_option == "🔢 Últimas X mensagens":
                    messages = self.deleter.get_user_messages(channel, limit=message_limit)
                
                # Deletar mensagens
                if messages:
                    def progress_callback(current, total, name):
                        if show_progress:
                            status_text.text(f"🗑️ Deletando {current}/{total} mensagens em {name}...")
                    
                    channel_deleted = self.deleter.safe_delete_messages(
                        messages, 
                        channel, 
                        delay_range=(min_delay, max_delay),
                        progress_callback=progress_callback
                    )
                    total_deleted += channel_deleted
                    
                    if show_progress:
                        st.success(f"✅ {channel_deleted} mensagens deletadas de {channel_name}")
                else:
                    st.info(f"ℹ️ Nenhuma mensagem encontrada em {channel_name}")
                
            except Exception as e:
                st.error(f"❌ Erro ao processar {channel_name}: {str(e)}")
            
            # Atualizar progresso
            progress_bar.progress((i + 1) / total_channels)
            time.sleep(2)  # Aumentado delay entre canais para evitar rate limits
        
        progress_bar.empty()
        status_text.empty()
        
        # Mostrar resultados finais
        with results_placeholder.container():
            st.success(f"🎉 Limpeza concluída! Total de mensagens deletadas: {total_deleted}")
            
            # Mostrar estatísticas
            stats = self.deleter.get_stats()
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.metric("Canais Processados", total_channels)
            
            with col2:
                st.metric("Mensagens Deletadas", total_deleted)
            
            with col3:
                st.metric("Falhas", stats['failed_count'])
            
            with col4:
                st.metric("Rate Limits", stats['throttled_count'])
            
            # Resetar estatísticas para próxima execução
            self.deleter.reset_stats()
    
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
    app = DiscordMessageDeleterApp()
    app.run()