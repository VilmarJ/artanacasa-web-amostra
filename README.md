# Web Artana — Sistema Web de Integração entre ERP x E-commerce

Sistema web desenvolvido com Flask para integração entre o ERP Tiny e a plataforma de e-commerce Magazord.

Permite consultar produtos cadastrados no Tiny, visualizar detalhes, e enviá-los automaticamente para a Magazord junto com mídias, estoque, preço e configurações de SEO. Também possui uma conexão junto ao Google Drive para armazenamento e controle das mídias (fotos e gifs) dos produtos.

---

## Funcionalidades

- Login e cadastro de usuários com senha criptografada (bcrypt)
- Recuperação de senha via e-mail e usuário
- Consulta de produtos no Tiny por data de criação
- Visualização de detalhes do produto (variações, dimensões, NCM, GTIN etc.)
- Integração completa com a Magazord:
  - Cadastro de produto pai e derivações (variações por cor/tamanho)
  - Envio de estoque e preço por derivação
  - Upload de mídias via Google Drive (base64)
  - Atualização de SEO (meta description) por página de produto

---

## Tecnologias

- Python 3.11+
- Flask
- SQLite (banco de usuários local)
- bcrypt (hash de senhas)
- Google Drive API v3
- Tiny ERP API v2
- Magazord API v1
- BeautifulSoup (processamento de descrições HTML)

---

## Estrutura

```
github/
├── app.py                      # Rotas Flask e demais lógicas
├── database.py                 # Cria a conexão com o banco de dados local
├── drive_utils.py              # Autenticação com o Google Drive
├── static/
│   ├── styles_esqueci.css      # Estilização da tela de esqueci a senha
│   ├── styles_index.css        # Estilização da pagina principal 
│   ├── styles_inicio.css       # Estilização da tela incial pós login
│   ├── styles_reset.css        # Estilização da tela de nova senha
│
├── templates/
│   ├── index.html              # Tela de login
│   ├── register.html           # Cadastro de usuário
│   ├── inicio.html             # Tela principal (desenvolvido com html + javascript internos)
│   ├── esqueci_senha.html      # Recuperação de senha
│   └── nova_senha.html         # Redefinição de senha
```
---

## Segurança

- Senhas armazenadas com hash bcrypt
- Credenciais carregadas via variáveis de ambiente
- Arquivos sensíveis (`credentials.json`, `token.pickle`, `.env`, banco de dados) protegidos pelo `.gitignore`

  ---

  # Imagem da tela de início do sistema
  <img width="1890" height="502" alt="image" src="https://github.com/user-attachments/assets/b04b5f3e-46a4-49cf-b3f1-c07c1cd41984" />

