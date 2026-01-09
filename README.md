# 🗑️ Discord Message Deleter

<div align="center">

![Discord Message Deleter](Discord-Message-Deleter.webp)

[![Python](https://img.shields.io/badge/Python-3.12-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.51.0-FF4B4B?style=for-the-badge&logo=streamlit&logoColor=white)](https://streamlit.io/)
[![Selenium](https://img.shields.io/badge/Selenium-4.38.0-43B02A?style=for-the-badge&logo=selenium&logoColor=white)](https://www.selenium.dev/)
[![License](https://img.shields.io/badge/License-MIT-yellow?style=for-the-badge)](LICENSE)

**A powerful and user-friendly tool to bulk delete your Discord messages from DMs and server channels.**

[Features](#-features) • [Installation](#-installation) • [Usage](#-usage) • [Support](#-support)

</div>

---

## ✨ Features

| Feature | Description |
|---------|-------------|
| 🔐 **Secure Login** | Login with your Discord credentials with 2FA support |
| 📊 **Interactive Dashboard** | View your DMs, servers, and channels in a beautiful UI |
| 💬 **Manage DMs** | Select and delete messages from direct messages and group chats |
| 🏠 **Manage Servers** | Browse servers and select specific channels for cleanup |
| ✅ **Bulk Selection** | Select all DMs or channels with one click |
| 🔍 **Search & Filter** | Easily find specific DMs or servers by name |
| 🚀 **Quick Delete** | One-click delete for individual conversations or channels |
| 📈 **Real-time Progress** | Live updates on deletion progress |
| 🎨 **Modern UI** | Discord-themed interface with dark mode |
| 💝 **PIX Donations** | Support the developer via PIX (Brazilian instant payment) |

---

## 🛠️ Tech Stack

- **[Python 3.12](https://www.python.org/)** - Core programming language
- **[Streamlit](https://streamlit.io/)** - Web application framework
- **[Selenium](https://www.selenium.dev/)** - Browser automation for secure login
- **[TLS Client](https://pypi.org/project/tls-client/)** - HTTP requests with TLS fingerprinting
- **[HTTPX](https://www.python-httpx.org/)** - Async HTTP client

---

## 📋 Requirements

- **Python 3.12** or higher
- **Google Chrome** browser installed
- **Internet connection** for installation

---

## 🚀 Installation

### Quick Install (Windows)

1. **Install Python**
   - Download from [python.org](https://www.python.org/downloads/)
   - ☑️ **Important:** Check "Add python.exe to PATH" during installation

2. **Extract the project**
   - Unzip the files to a folder (e.g., `C:\DiscordMessageDeleter`)

3. **Install dependencies**
   - Double-click `install.bat`
   - Wait for installation (2-5 minutes)

### Manual Install

```bash
# Clone the repository
git clone https://github.com/MathSchumacher/Discord-message-deleter.git

# Navigate to the directory
cd Discord-message-deleter

# Install dependencies
pip install -r requirements.txt
```

---

## 📖 Usage

### Quick Start (Windows)

1. Double-click `run.bat`
2. Wait for the browser to open automatically at `http://localhost:8501`
3. Login with your Discord credentials
4. Start managing your messages!

### Manual Start

```bash
# Run the application
python -m streamlit run app.py --server.port=8501 --server.headless=true
```

### How to Use

1. **Login** - Enter your Discord email and password
   - Check the 2FA box if you have two-factor authentication enabled
   - The browser will open for you to complete 2FA if needed

2. **Dashboard** - View your account overview
   - See total DMs, servers, and connection status
   - Quick access to recent conversations

3. **Manage DMs** - Select direct messages for deletion
   - Use "Select All" or pick individually
   - Search by username or display name
   - Quick delete button for each DM

4. **Manage Servers** - Browse your servers and channels
   - Expand servers to see text channels
   - Select specific channels for cleanup
   - Owner badge (👑) for servers you own

5. **Configure Cleanup** - Fine-tune deletion settings
   - Set date ranges
   - Configure delay between deletions
   - Start the cleanup process

---

## ⚠️ Important Notes

> **🔒 Security:** Your credentials are used only for authentication. The token is stored locally and never shared.

> **⏱️ Rate Limits:** Discord has rate limits. The app includes delays to avoid triggering them.

> **📱 Avoid Multi-Device:** Don't use your Discord account on other devices while the cleanup is running.

> **💾 Irreversible:** Deleted messages cannot be recovered. Use with caution!

---

## 🆘 Troubleshooting

| Issue | Solution |
|-------|----------|
| `run.bat` doesn't work | Create a desktop shortcut with: `cmd /k "cd /d C:\path\to\folder && python -m streamlit run app.py"` |
| Chrome doesn't open | Ensure Google Chrome is installed |
| Permission error | Run `.bat` files as Administrator |
| Login fails | Check your credentials and try again |

---

## 💝 Support the Developer

If you find this tool useful, consider supporting the development!

<div align="center">

![PIX QR Code](img/qrcode.webp)

**PIX Key:** `matheusmschumacher@gmail.com`

</div>

---

## 📧 Contact

- **Email:** matheusmschumacher@gmail.com
- **GitHub:** [@MathSchumacher](https://github.com/MathSchumacher)

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

<div align="center">

**Made with ❤️ by [Matheus Schumacher](https://github.com/MathSchumacher)**

⭐ Star this repository if you found it helpful!

</div>
