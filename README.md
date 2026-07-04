# Organizador de Arquivos Inteligente para macOS 🚀

Um organizador de arquivos inteligente, de alta performance e otimizado para macOS. Reorganiza fotos, vídeos, áudios e documentos utilizando metadados internos, geocodificação de localização, inteligência artificial local nativa do macOS e opcionalmente o Google Gemini. 

Também possui suporte dedicado para renomear coleções de livros digitais (PDF e EPUB) e conta com uma interface gráfica local moderna baseada em web.

---

## ✨ Recursos Principais

- **Extração Avançada de Metadados**:
  - **Fotos**: Lê datas de captura (EXIF) e coordenadas de GPS. Suporte nativo para formatos HEIC/HEIF (iPhone).
  - **Vídeos**: Lê metadados e coordenadas de localização embutidas (gravadas por celulares).
  - **Áudio**: Extrai dados de tags (MP3, M4A, FLAC, etc.).
  - **Fallback Temporal**: Em arquivos sem metadados, utiliza a data de criação real do arquivo no macOS (`st_birthtime`).
- **Geocodificação Reversa com Cache Local**:
  - Converte latitude e longitude em país, estado e cidade via Nominatim API.
  - Utiliza um banco de dados local **SQLite** (`~/.file_organizer/geocoding_cache.db`) e arredondamento de coordenadas para garantir velocidade instantânea e zero desperdício de requisições.
- **Inteligência Local macOS (Vision & OCR)**:
  - Integra-se com os frameworks nativos do macOS usando código compilado em Swift.
  - Classifica imagens localmente (identifica fotos de praia, natureza, retrato, comida, etc.) de forma **100% gratuita, offline e sem limite de requisições**.
  - Executa **OCR de alta velocidade** localmente para identificar e separar documentos específicos sem GPS (ex: comprovantes bancários, prints de tela, mídias de WhatsApp/Instagram, mapas e anotações).
- **Renomeação Inteligente por IA (Opcional)**:
  - Suporte ao novo SDK `google-genai` para classificar arquivos de imagem usando o modelo `gemini-2.5-flash`.
  - Mecanismo de contingência automático: desativa requisições e adota o modelo local se a cota do Gemini for excedida (`429 Quota Exceeded`).
- **Organizador de Livros**:
  - Lê e renomeia coleções de livros em formato PDF e EPUB utilizando metadados internos e análise textual para o padrão `Autor - Título do Livro`.
- **Interface Gráfica Local (Web UI)**:
  - Painel com design moderno (*Dark Mode* e *Glassmorphism*).
  - Botões que abrem a **caixa de diálogo nativa do Finder do macOS** para escolha de pastas.
  - Barra de progresso animada e console de logs em tempo real via **Server-Sent Events (SSE)**.

---

## 📂 Estrutura de Arquivos

```text
├── main.py                    # Ponto de entrada da CLI
├── organizer_server.py        # Servidor local para a interface web
├── index.html                 # Frontend da interface web (HTML/CSS/JS)
├── organizer_credentials.json # [Ignorado pelo Git] Credenciais da API do Gemini
├── requirements.txt           # Dependências de bibliotecas Python
├── tests/                     # Testes de unidade do aplicativo
│   └── test_organizer.py
└── organizer/                 # Módulos principais do core
    ├── cli.py                 # Parser de argumentos CLI e logs
    ├── processor.py           # Orquestrador de leitura e movimentação física
    ├── metadata.py            # Módulo de extração de EXIF/Tags
    ├── geocoder.py            # Localizador de GPS e Cache SQLite
    ├── ai_tagger.py           # Integração com Gemini API / Local macOS Vision
    ├── mac_tagger.swift       # Código nativo Swift para classificação e OCR
    ├── mac_tagger             # [Compilado] Binário Swift de alta performance
    └── rename_books.py        # Módulo de processamento de livros
```

---

## ⚙️ Instalação e Configuração

### 1. Preparar Ambiente e Instalar Dependências
Certifique-se de estar usando o Python 3 instalado no macOS. Crie um ambiente virtual e instale as dependências:
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Compilar o Módulo Nativo do macOS (Swift)
Compile o arquivo auxiliar Swift para gerar o binário otimizado de Vision/OCR:
```bash
swiftc -O organizer/mac_tagger.swift -o organizer/mac_tagger
```

### 3. Configurar API do Gemini (Opcional)
Crie um arquivo chamado `organizer_credentials.json` na raiz do projeto contendo sua chave (esse arquivo já está listado no `.gitignore` por segurança):
```json
{
  "gemini_api_key": "SUA_CHAVE_AQUI",
  "project_name": "Organizador-Fotos"
}
```

---

## 🚀 Como Utilizar

### Modo 1: Interface Gráfica (Web UI)
Esta é a forma mais fácil e visual de operar o aplicativo:

1. Inicie o servidor da interface:
   ```bash
   ./venv/bin/python3 organizer_server.py
   ```
2. Abra seu navegador em: **[http://localhost:8080](http://localhost:8080)**.
3. Clique em **Selecionar** para abrir o Finder nativo, escolha a pasta de origem, de destino, configure as opções visuais e clique em **Iniciar Organização**. O console exibirá o andamento em tempo real.

---

### Modo 2: Linha de Comando (CLI)
Para controle avançado via terminal:

```bash
# Executar uma simulação (Dry-Run) sem alterar nenhum arquivo físico no disco
./venv/bin/python3 main.py --src "/caminho/origem" --dest "/caminho/destino" --folder-format "{country}/{year}/{ai_tag}" --ai-rename --dry-run

# Executar a organização real copiando arquivos (Recomendado)
./venv/bin/python3 main.py --src "/caminho/origem" --dest "/caminho/destino" --folder-format "{country}/{year}/{ai_tag}" --ai-rename --action copy

# Executar limitando apenas aos primeiros 50 arquivos
./venv/bin/python3 main.py --src "/caminho/origem" --dest "/caminho/destino" --folder-format "{country}/{year}/{ai_tag}" --ai-rename --limit 50
```

#### Variáveis suportadas no `--folder-format` e `--file-format`:
* `{country}`: País geolocalizado (ex: `Brasil`, `Itália`) ou `Z - Outros` se não houver coordenadas.
* `{state}`: Estado da localização.
* `{city}`: Cidade da localização.
* `{year}`: Ano da foto/mídia.
* `{month}`: Mês da foto/mídia (formato numérico `01`, `02`).
* `{day}`: Dia do mês.
* `{ai_tag}`: Categoria (ex: `natureza_ou_paisagem`, `retrato`, `screenshot`).
* `{original_name}`: Nome original do arquivo.
* `{ext}`: Extensão original do arquivo (minúscula).

---

### Modo 3: Organizar Livros Digitais
Para renomear coleções de livros na pasta de livros:
```bash
./venv/bin/python3 organizer/rename_books.py
```

---

## 🧪 Rodando Testes Unitários
Para verificar se todos os módulos (geocoder, tagger local, processor e metadados) estão íntegros:
```bash
./venv/bin/python3 -m unittest discover -s tests
```
