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

## 🐧 Configuração (Linux)

1. **Navegue até o diretório**:
   ```bash
   cd /caminho/para/MAPA-REDE
   ```

2. **Crie e ative o ambiente virtual**:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3. **Instele as dependências**:
   ```bash
   pip install -r requirements.txt
   ```

---

## 🏃 Como Rodar

1. **Inicie a aplicação**:
   ```bash
   python app.py
   ```

2. **Acesse no navegador**:
   Abra o endereço [http://localhost:5050](http://localhost:5050)

---

## 📁 Estrutura de Pastas Úteis
- `app.py`: Servidor Flask e lógica de scan.
- `models.py`: Gerenciamento do banco de dados SQLite.
- `snmp_handler.py`: Comunicação SNMP e descoberta LLDP.
- `EXCLUIR/`: Scripts de utilidade e debug (arquivados).
