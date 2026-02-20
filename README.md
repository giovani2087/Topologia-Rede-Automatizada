# Mapa de Rede - Monitoramento SNMP & LLDP

Este projeto é uma aplicação web baseada em Flask para descoberta e visualização de topologia de rede utilizando SNMP e LLDP.

## 🚀 Pré-requisitos

- **Python 3.10 ou superior**
- Acesso à rede para dispositivos com SNMP habilitado (v2c).
- Comunidade SNMP configurada em seus dispositivos (ex: `public`).

---

## 💻 Configuração (Windows)

1. **Abra o PowerShell ou Prompt de Comando** no diretório do projeto:
   ```powershell
   cd C:\tmp\MAPA-REDE
   ```

2. **Crie um ambiente virtual**:
   ```powershell
   python -m venv .venv
   ```

3. **Ative o ambiente virtual**:
   - PowerShell: `.\.venv\Scripts\Activate.ps1`
   - CMD: `.\.venv\Scripts\activate.bat`

4. **Instale as dependências**:
   ```powershell
   pip install -r requirements.txt
   ```

---

## 🐧 Configuração (Linux - Ubuntu/Debian)

Em versões recentes (como Ubuntu 24.04), o Python protege o sistema contra instalações globais via `pip`. Você **deve** usar um ambiente virtual (`venv`).

1. **Instale os pré-requisitos do sistema**:
   ```bash
   sudo apt update
   sudo apt install -y python3-pip python3-venv
   ```

2. **Navegue até o diretório e crie o ambiente virtual**:
   ```bash
   # Navegue para onde o projeto foi baixado
   cd /caminho/para/Topologia-Rede-Automatizada
   python3 -m venv .venv
   ```

3. **Ative o ambiente virtual (IMPORTANTE)**:
   ```bash
   source .venv/bin/activate
   ```
   *Após a ativação, o nome `(.venv)` aparecerá no início da sua linha de comando.*

4. **Instale as dependências dentro da venv**:
   ```bash
   pip install -r requirements.txt
   ```

---

## 🏃 Como Rodar

1. **Certifique-se de que a venv está ativa** e inicie a aplicação:
   ```bash
   python3 app.py
   ```

2. **Acesse no navegador**:
   Abra o endereço [http://localhost:5050](http://localhost:5050)

---

## 📁 Estrutura de Pastas Úteis
- `app.py`: Servidor Flask e lógica de scan.
- `models.py`: Gerenciamento do banco de dados SQLite.
- `snmp_handler.py`: Comunicação SNMP e descoberta LLDP.
- `EXCLUIR/`: Scripts de utilidade e debug (arquivados).
