import os
import re
import html
import base64
import pickle

import bcrypt
import requests
from io import BytesIO
from datetime import datetime

from flask import Flask, render_template, request, redirect, jsonify, session, url_for
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from bs4 import BeautifulSoup
from dotenv import load_dotenv

from database import pegar_banco

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("CHAVE_SECRETA")

with open("token.pickle", "rb") as arquivo_token:
    credenciais = pickle.load(arquivo_token)
servico_drive = build("drive", "v3", credentials=credenciais)

#feito hardcoded temporariamente
URL_TINY      = os.getenv("TINY_URL")
TOKEN_TINY    = os.getenv("TINY_TOKEN")
URL_MAGAZORD  = os.getenv("MAGAZORD_URL")
TOKEN_MAGAZORD = os.getenv("MAGAZORD_TOKEN")
SENHA_MAGAZORD = os.getenv("MAGAZORD_SENHA")


@app.route("/")
def pagina_login():
    return render_template("index.html")


@app.route("/login", methods=["POST"])
def fazer_login():
    usuario = request.form.get("usuario")
    senha   = request.form.get("senha")

    conn   = pegar_banco()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM usuarios WHERE usuario = ?", (usuario,))
    usuario_encontrado = cursor.fetchone()
    conn.close()

    if usuario_encontrado and bcrypt.checkpw(senha.encode(), usuario_encontrado["senha"].encode()):
        session["usuario"] = usuario_encontrado["usuario"]
        return redirect(url_for("tela_inicial"))

    return render_template("index.html", erro="Usuário ou senha incorretos.")


@app.route("/cadastro", methods=["GET", "POST"])
def cadastro():
    if request.method == "GET":
        return render_template("register.html")

    usuario = request.form.get("usuario")
    email   = request.form.get("email")
    senha   = request.form.get("senha")

    senha_hash = bcrypt.hashpw(senha.encode(), bcrypt.gensalt()).decode()

    conn   = pegar_banco()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO usuarios (usuario, email, senha) VALUES (?, ?, ?)",
            (usuario, email, senha_hash)
        )
        conn.commit()
        conn.close()
        return redirect("/")
    except Exception:
        conn.close()
        return render_template("register.html", erro="Usuário ou e-mail já cadastrado.")


@app.route("/esqueci-senha")
def esqueci_senha():
    return render_template("esqueci_senha.html")


@app.route("/verificar-reset", methods=["POST"])
def verificar_reset():
    usuario = request.form.get("usuario")
    email   = request.form.get("email")

    conn   = pegar_banco()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM usuarios WHERE usuario = ? AND email = ?", (usuario, email))
    encontrado = cursor.fetchone()
    conn.close()

    if encontrado:
        return render_template("nova_senha.html", usuario=usuario)

    return render_template("esqueci_senha.html", erro="Usuário e e-mail não encontrados.")


@app.route("/resetar-senha", methods=["POST"])
def resetar_senha():
    usuario    = request.form.get("usuario")
    nova_senha = request.form.get("nova_senha")

    nova_senha_hash = bcrypt.hashpw(nova_senha.encode(), bcrypt.gensalt()).decode()

    conn   = pegar_banco()
    cursor = conn.cursor()
    cursor.execute("UPDATE usuarios SET senha = ? WHERE usuario = ?", (nova_senha_hash, usuario))
    conn.commit()
    conn.close()

    return render_template("index.html", msg="Senha redefinida com sucesso! Faça o login.")


@app.route("/inicio")
def tela_inicial():
    if "usuario" not in session:
        return redirect("/")
    return render_template("inicio.html", usuario=session["usuario"])


@app.route("/sair")
def sair():
    session.clear()
    return redirect("/")


@app.route("/consultar", methods=["POST"])
def consultar_produtos():
    dados       = request.get_json()
    data_iso    = dados.get("dataCriacao")

    try:
        data_formatada = datetime.strptime(data_iso, "%Y-%m-%d").strftime("%d/%m/%Y")
    except Exception:
        data_formatada = ""

    parametros = {
        "token":       TOKEN_TINY,
        "formato":     "json",
        "idTag":       "921941623",
        "dataCriacao": data_formatada
    }

    try:
        resposta     = requests.get(f"{URL_TINY}/produtos.pesquisa.php", params=parametros)
        dados_api    = resposta.json()
    except Exception as erro:
        print(f"Erro ao consultar produtos: {erro}")
        return jsonify({"produtos": []}), 500

    lista_produtos = []
    for item in dados_api.get("retorno", {}).get("produtos", []):
        prod = item.get("produto", {})
        lista_produtos.append({
            "codigo":    prod.get("codigo", ""),
            "nome":      prod.get("nome", ""),
            "idProduto": prod.get("id", "")
        })

    return jsonify({"produtos": lista_produtos})


@app.route("/detalhes_produto", methods=["POST"])
def detalhes_produto():
    dados      = request.get_json()
    id_produto = dados.get("idProduto", "")

    if not id_produto:
        return jsonify({"erro": "idProduto não informado"}), 400

    parametros = {"token": TOKEN_TINY, "formato": "json", "id": id_produto}

    try:
        resposta     = requests.get(f"{URL_TINY}/produto.obter.php", params=parametros)
        produto_info = resposta.json().get("retorno", {}).get("produto", {})
    except Exception as erro:
        print(f"Erro ao obter detalhes do produto {id_produto}: {erro}")
        return jsonify({"erro": "Erro ao obter detalhes"}), 500

    nome_marca = produto_info.get("marca", "")
    id_marca   = obter_id_marca_magazord(nome_marca) if nome_marca else None

    return jsonify({
        "nome":                   produto_info.get("nome", ""),
        "codigo":                 produto_info.get("codigo", ""),
        "preco":                  produto_info.get("preco", 0),
        "tipoVariacao":           produto_info.get("tipoVariacao", ""),
        "marca":                  id_marca,
        "categoria":              produto_info.get("categoria", ""),
        "variacoes":              produto_info.get("variacoes", []),
        "ncm":                    produto_info.get("ncm", ""),
        "garantia":               produto_info.get("garantia", ""),
        "gtin":                   produto_info.get("gtin", ""),
        "cest":                   produto_info.get("cest", ""),
        "unidade":                produto_info.get("unidade", ""),
        "peso_bruto":             produto_info.get("peso_bruto", ""),
        "alturaEmbalagem":        produto_info.get("alturaEmbalagem"),
        "larguraEmbalagem":       produto_info.get("larguraEmbalagem"),
        "comprimentoEmbalagem":   produto_info.get("comprimentoEmbalagem"),
        "descricao_complementar": produto_info.get("descricao_complementar"),
        "palavra_chave":          produto_info.get("seo_keywords")
    })


@app.route("/integrar", methods=["POST"])
def integrar_produtos():
    produtos   = request.get_json(force=True)
    integrados = []
    falhas     = []

    for prod_pai in produtos:
        try:
            largura_img = prod_pai.get("imgWidth", "503")
            altura_img  = prod_pai.get("imgHeight", "381")

            parametros   = {"token": TOKEN_TINY, "formato": "json", "id": prod_pai["idProduto"]}
            resposta     = requests.get(f"{URL_TINY}/produto.obter.php", params=parametros, timeout=10)
            produto_info = resposta.json().get("retorno", {}).get("produto", {})

            nome_categoria  = produto_info.get("categoria")
            id_categoria    = buscar_categoria_magazord(nome_categoria)
            descricao_seo   = prod_pai.get("seo_description", "")

            prod_pai["variacoes"]    = produto_info.get("variacoes", [])
            prod_pai["tipoVariacao"] = produto_info.get("tipoVariacao")
            prod_pai["preco"]        = produto_info.get("preco", 0)

            nome_marca = prod_pai.get("marca", "")
            id_marca   = obter_id_marca_magazord(nome_marca) if nome_marca else None
            derivacoes = mapear_derivacoes(prod_pai)

            descricao_processada = processar_descricao(
                prod_pai.get("descricao_complementar", ""),
                prod_pai.get("codigo"),
                largura_img=largura_img,
                altura_img=altura_img
            )

            corpo_produto = {
                "codigo":         prod_pai.get("codigo"),
                "nome":           prod_pai.get("nome"),
                "marca":          id_marca,
                "origemFiscal":   0,
                "ativo":          True,
                "acompanha":      prod_pai.get("acompanha", ""),
                "palavraChave":   prod_pai.get("palavra_chave", ""),
                "peso":           float(prod_pai.get("peso_bruto", 0)),
                "altura":         float(prod_pai.get("alturaEmbalagem", 0)),
                "largura":        float(prod_pai.get("larguraEmbalagem", 0)),
                "comprimento":    float(prod_pai.get("comprimentoEmbalagem", 0)),
                "unidadeMedida":  prod_pai.get("unidade", ""),
                "ncm":            prod_pai.get("ncm", ""),
                "cest":           prod_pai.get("cest", ""),
                "derivacoes":     derivacoes,
                "categorias":     [id_categoria],
                "garantias":      [2],
                "produtoLoja": [{
                    "loja":              1,
                    "descricao":         descricao_processada,
                    "descricaoResumida": prod_pai.get("descricao_resumida", "")
                }]
            }

            url_produto = f"{URL_MAGAZORD}/api/v2/site/produto"
            resposta_produto = requests.post(
                url_produto,
                auth=(TOKEN_MAGAZORD, SENHA_MAGAZORD),
                json=corpo_produto
            )

            if resposta_produto.status_code in [200, 201]:
                integrados.append({
                    "idProduto": prod_pai.get("idProduto"),
                    "codigo":    prod_pai.get("codigo"),
                    "tipo":      "pai"
                })

            variacoes = prod_pai.get("variacoes", [])
            tipo_var  = prod_pai.get("tipoVariacao", "N")

            if tipo_var == "N":
                codigo_filho    = prod_pai.get("codigo") + "-1"
                preco_filho     = prod_pai.get("preco", 0)
                derivacoes_filho = [{"derivacao": 3, "valor": "Único"}]

                corpo_filho = {
                    "codigo":     codigo_filho,
                    "nome":       prod_pai.get("nome", ""),
                    "ativo":      True,
                    "ean":        prod_pai.get("gtin", ""),
                    "derivacoes": derivacoes_filho,
                    "lojas":      [1]
                }

                url_filho    = f"{URL_MAGAZORD}/api/v2/site/produto/{prod_pai.get('codigo')}/derivacao"
                resp_filho   = requests.post(url_filho, auth=(TOKEN_MAGAZORD, SENHA_MAGAZORD), json=corpo_filho)

                if resp_filho.status_code not in [200, 201]:
                    falhas.append({
                        "idProduto":   prod_pai.get("idProduto"),
                        "codigo":      codigo_filho,
                        "mensagem":    resp_filho.text,
                        "status_code": resp_filho.status_code,
                        "tipo":        "filho"
                    })
                else:
                    integrados.append({
                        "idProduto": prod_pai.get("idProduto"),
                        "codigo":    codigo_filho,
                        "tipo":      "filho"
                    })

                params_estoque  = {"token": TOKEN_TINY, "formato": "json", "id": prod_pai.get("idProduto")}
                resp_estoque    = requests.get(f"{URL_TINY}/produto.obter.estoque.php", params=params_estoque)
                saldo_estoque   = resp_estoque.json().get("retorno", {}).get("produto", {}).get("saldo", 0)

                corpo_estoque = {
                    "produto":       codigo_filho,
                    "deposito":      1,
                    "quantidade":    saldo_estoque,
                    "tipo":          1,
                    "tipoOperacao":  0,
                    "observacao":    "Enviado via sistema web"
                }

                envio_estoque = requests.post(
                    f"{URL_MAGAZORD}/api/v1/estoque",
                    auth=(TOKEN_MAGAZORD, SENHA_MAGAZORD),
                    json=corpo_estoque
                )

                try:
                    retorno_estoque = envio_estoque.json()
                except ValueError:
                    retorno_estoque = {"status": "error", "mensagem": envio_estoque.text}

                if retorno_estoque.get("status") == "error" or envio_estoque.status_code not in [200, 201]:
                    falhas.append({
                        "idProduto":   prod_pai.get("idProduto"),
                        "codigo":      codigo_filho,
                        "mensagem":    retorno_estoque.get("mensagem", envio_estoque.text),
                        "status_code": envio_estoque.status_code,
                        "tipo":        "estoque"
                    })
                else:
                    integrados.append({
                        "idProduto":      prod_pai.get("idProduto"),
                        "codigo":         codigo_filho,
                        "tipo":           "estoque",
                        "mensagem":       retorno_estoque.get("mensagem"),
                        "id_movimentacao": retorno_estoque.get("movimentacao_id", 0)
                    })

                corpo_preco = [{
                    "produto":      codigo_filho,
                    "tabelaPreco":  1,
                    "precoAntigo":  0,
                    "precoVenda":   preco_filho
                }]

                envio_preco = requests.post(
                    f"{URL_MAGAZORD}/api/v1/preco",
                    auth=(TOKEN_MAGAZORD, SENHA_MAGAZORD),
                    json=corpo_preco
                )

                try:
                    retorno_preco = envio_preco.json()
                except ValueError:
                    retorno_preco = {"sucesso": False, "mensagem": envio_preco.text}

                if retorno_preco.get("sucesso") is False or envio_preco.status_code not in [200, 201]:
                    falhas.append({
                        "idProduto":   prod_pai.get("idProduto"),
                        "codigo":      codigo_filho,
                        "mensagem":    retorno_preco.get("mensagem", envio_preco.text),
                        "status_code": envio_preco.status_code,
                        "tipo":        "preco"
                    })
                else:
                    integrados.append({
                        "idProduto": prod_pai.get("idProduto"),
                        "codigo":    codigo_filho,
                        "tipo":      "preco",
                        "mensagem":  retorno_preco.get("mensagem")
                    })

            else:
                for variacao in variacoes:
                    var          = variacao.get("variacao", {})
                    codigo_filho = var.get("codigo")
                    grade        = var.get("grade", {})

                    derivacoes_filho = montar_derivacoes_filhos(grade)

                    corpo_filho = {
                        "codigo":     codigo_filho,
                        "nome":       prod_pai.get("nome", ""),
                        "ativo":      True,
                        "derivacoes": derivacoes_filho,
                        "lojas":      [1]
                    }

                    url_filho  = f"{URL_MAGAZORD}/api/v2/site/produto/{prod_pai.get('codigo')}/derivacao"
                    resp_filho = requests.post(url_filho, auth=(TOKEN_MAGAZORD, SENHA_MAGAZORD), json=corpo_filho)

                    if resp_filho.status_code not in [200, 201]:
                        falhas.append({
                            "idProduto":   prod_pai.get("idProduto"),
                            "codigo":      codigo_filho,
                            "mensagem":    resp_filho.text,
                            "status_code": resp_filho.status_code,
                            "tipo":        "filho"
                        })
                        continue

                    integrados.append({
                        "idProduto": prod_pai.get("idProduto"),
                        "codigo":    codigo_filho,
                        "tipo":      "filho"
                    })

                    id_filho    = var.get("id")
                    preco_filho = var.get("preco", 0)

                    params_estoque = {"token": TOKEN_TINY, "formato": "json", "id": id_filho}
                    resp_estoque   = requests.get(f"{URL_TINY}/produto.obter.estoque.php", params=params_estoque)
                    saldo_estoque  = resp_estoque.json().get("retorno", {}).get("produto", {}).get("saldo", 0)

                    corpo_estoque = {
                        "produto":      codigo_filho,
                        "deposito":     1,
                        "quantidade":   saldo_estoque,
                        "tipo":         1,
                        "tipoOperacao": 0,
                        "observacao":   "Enviado via sistema web"
                    }

                    envio_estoque = requests.post(
                        f"{URL_MAGAZORD}/api/v1/estoque",
                        auth=(TOKEN_MAGAZORD, SENHA_MAGAZORD),
                        json=corpo_estoque
                    )

                    try:
                        retorno_estoque = envio_estoque.json()
                    except ValueError:
                        retorno_estoque = {"status": "error", "mensagem": envio_estoque.text}

                    if retorno_estoque.get("status") == "error" or envio_estoque.status_code not in [200, 201]:
                        falhas.append({
                            "idProduto":   prod_pai.get("idProduto"),
                            "codigo":      codigo_filho,
                            "mensagem":    retorno_estoque.get("mensagem", envio_estoque.text),
                            "status_code": envio_estoque.status_code,
                            "tipo":        "estoque"
                        })
                    else:
                        integrados.append({
                            "idProduto":       prod_pai.get("idProduto"),
                            "codigo":          codigo_filho,
                            "tipo":            "estoque",
                            "mensagem":        retorno_estoque.get("mensagem"),
                            "id_movimentacao": retorno_estoque.get("movimentacao_id", 0)
                        })

                    corpo_preco = [{
                        "produto":     codigo_filho,
                        "tabelaPreco": 1,
                        "precoAntigo": 0,
                        "precoVenda":  preco_filho
                    }]

                    envio_preco = requests.post(
                        f"{URL_MAGAZORD}/api/v1/preco",
                        auth=(TOKEN_MAGAZORD, SENHA_MAGAZORD),
                        json=corpo_preco
                    )

                    try:
                        retorno_preco = envio_preco.json()
                    except ValueError:
                        retorno_preco = {"sucesso": False, "mensagem": envio_preco.text}

                    if retorno_preco.get("sucesso") is False or envio_preco.status_code not in [200, 201]:
                        falhas.append({
                            "idProduto":   prod_pai.get("idProduto"),
                            "codigo":      codigo_filho,
                            "mensagem":    retorno_preco.get("mensagem", envio_preco.text),
                            "status_code": envio_preco.status_code,
                            "tipo":        "preco"
                        })
                    else:
                        integrados.append({
                            "idProduto": prod_pai.get("idProduto"),
                            "codigo":    codigo_filho,
                            "tipo":      "preco",
                            "mensagem":  retorno_preco.get("mensagem")
                        })

            midias_encontradas = buscar_midias_drive(prod_pai.get("codigo"))
            arquivos_enviados  = []

            padrao = re.compile(r"^([0-4])\-")
            midias_filtradas = [
                (id_arq, nome_arq)
                for id_arq, nome_arq in midias_encontradas
                if padrao.match(nome_arq)
            ]

            for id_arquivo, nome_arquivo in midias_filtradas:
                try:
                    requisicao = servico_drive.files().get_media(fileId=id_arquivo)
                    buffer     = BytesIO()
                    downloader = MediaIoBaseDownload(buffer, requisicao)
                    concluido  = False
                    while not concluido:
                        _, concluido = downloader.next_chunk()

                    arquivo_base64 = base64.b64encode(buffer.getvalue()).decode("utf-8")
                    resultado_upload = enviar_midia_magazord(prod_pai.get("codigo"), arquivo_base64, nome_arquivo)
                    id_midia = resultado_upload.get("data", {}).get("id") if resultado_upload.get("status") == "success" else None

                    if id_midia:
                        vincular_midia_produto(prod_pai.get("codigo"), prod_pai.get("codigo"), id_midia)
                        integrados.append({
                            "idProduto":  prod_pai.get("idProduto"),
                            "codigo":     prod_pai.get("codigo"),
                            "nome_midia": nome_arquivo,
                            "tipo":       "midia",
                            "id_midia":   id_midia
                        })
                        arquivos_enviados.append((id_arquivo, nome_arquivo))
                    else:
                        falhas.append({
                            "idProduto":  prod_pai.get("idProduto"),
                            "codigo":     prod_pai.get("codigo"),
                            "nome_midia": nome_arquivo,
                            "mensagem":   f"Falha no upload: {resultado_upload}",
                            "tipo":       "midia"
                        })

                except Exception as erro:
                    falhas.append({
                        "idProduto": prod_pai.get("idProduto"),
                        "codigo":    prod_pai.get("codigo"),
                        "mensagem":  f"Erro ao processar mídia '{nome_arquivo}': {erro}",
                        "tipo":      "midia"
                    })

            if arquivos_enviados:
                sucesso_copia = copiar_midias_para_categoria(arquivos_enviados, nome_categoria)
                if not sucesso_copia:
                    falhas.append({
                        "idProduto": prod_pai.get("idProduto"),
                        "codigo":    prod_pai.get("codigo"),
                        "mensagem":  f"Pasta da categoria '{nome_categoria}' não encontrada.",
                        "tipo":      "midia"
                    })

            try:
                parametros_seo = {"codigoDerivacao": codigo_filho}
                url_paginas    = f"{URL_MAGAZORD}/api/v2/site/paginas"
                resp_pagina    = requests.get(url_paginas, auth=(TOKEN_MAGAZORD, SENHA_MAGAZORD), params=parametros_seo)

                if resp_pagina.status_code == 200:
                    itens_pagina = resp_pagina.json().get("data", {}).get("items", [])
                    if itens_pagina:
                        id_pagina  = itens_pagina[0].get("id")
                        corpo_seo  = {"metaDescription": descricao_seo}
                        url_seo    = f"{url_paginas}/{id_pagina}"
                        resp_seo   = requests.patch(url_seo, auth=(TOKEN_MAGAZORD, SENHA_MAGAZORD), json=corpo_seo)

                        if resp_seo.status_code == 200:
                            integrados.append({
                                "idProduto": prod_pai.get("idProduto"),
                                "codigo":    prod_pai.get("codigo"),
                                "tipo":      "seo",
                                "id_pagina": id_pagina,
                                "mensagem":  "SEO atualizado com sucesso."
                            })
                        else:
                            falhas.append({
                                "idProduto": prod_pai.get("idProduto"),
                                "codigo":    prod_pai.get("codigo"),
                                "tipo":      "seo",
                                "mensagem":  f"Falha ao atualizar SEO: {resp_seo.text}"
                            })
                    else:
                        falhas.append({
                            "idProduto": prod_pai.get("idProduto"),
                            "codigo":    prod_pai.get("codigo"),
                            "tipo":      "seo",
                            "mensagem":  f"Página não encontrada para o código {codigo_filho}"
                        })

            except Exception as erro:
                falhas.append({
                    "idProduto": prod_pai.get("idProduto"),
                    "codigo":    prod_pai.get("codigo"),
                    "tipo":      "seo",
                    "mensagem":  f"Erro ao atualizar SEO: {erro}"
                })

        except Exception as erro:
            falhas.append({
                "idProduto":   prod_pai.get("idProduto"),
                "codigo":      prod_pai.get("codigo"),
                "mensagem":    str(erro),
                "status_code": None,
                "tipo":        "pai/filho"
            })

    situacao = "sucesso" if not falhas else "erro"
    return jsonify({"status": situacao, "integrados": integrados, "falhas": falhas})


def buscar_pasta_drive(nome, pasta_pai_id=None):
    consulta = f"name = '{nome}' and mimeType = 'application/vnd.google-apps.folder' and trashed=false"
    if pasta_pai_id:
        consulta += f" and '{pasta_pai_id}' in parents"
    resultado = servico_drive.files().list(q=consulta, fields="files(id, name)", pageSize=10).execute()
    arquivos  = resultado.get("files", [])
    return arquivos[0]["id"] if arquivos else None


def buscar_midias_drive(codigo_produto: str):
    def encontrar_pasta_sku(codigo, pasta_pai_id):
        resultado = servico_drive.files().list(
            q=f"'{pasta_pai_id}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false",
            fields="files(id, name)",
            pageSize=100
        ).execute()
        pastas = resultado.get("files", [])
        for pasta in pastas:
            if pasta["name"].strip().lower() == codigo.strip().lower():
                return pasta["id"]
            sub_id = encontrar_pasta_sku(codigo, pasta["id"])
            if sub_id:
                return sub_id
        return None

    try:
        id_artana    = buscar_pasta_drive("ARTANA")
        id_midias    = buscar_pasta_drive("03_Mídias", id_artana)
        id_organizado = buscar_pasta_drive("03_Organizado por Marca e SKU", id_midias)

        if not all([id_artana, id_midias, id_organizado]):
            return []

        id_sku = encontrar_pasta_sku(codigo_produto, id_organizado)
        if not id_sku:
            return []

        resultado = servico_drive.files().list(
            q=f"'{id_sku}' in parents and trashed=false",
            fields="files(id, name)",
            pageSize=100
        ).execute()
        arquivos = resultado.get("files", [])

        padrao = re.compile(r"^(\d+)-")
        arquivos_filtrados = []
        for arq in arquivos:
            correspondencia = padrao.match(arq["name"])
            if correspondencia:
                numero = int(correspondencia.group(1))
                arquivos_filtrados.append((numero, arq))

        arquivos_ordenados = sorted(arquivos_filtrados, key=lambda x: x[0])
        return [(arq["id"], arq["name"]) for _, arq in arquivos_ordenados]

    except Exception as erro:
        print(f"Erro ao buscar mídias: {erro}")
        return []


def enviar_midia_magazord(codigo_produto, arquivo_base64, nome_arquivo):
    url_midia  = f"{URL_MAGAZORD}/api/v2/site/midia/upload"
    corpo_midia = {
        "tipo":        1,
        "plataforma":  1,
        "tipoMidia":   1,
        "midiaFile":   arquivo_base64,
        "nomeArquivo": nome_arquivo
    }
    try:
        resposta  = requests.post(url_midia, auth=(TOKEN_MAGAZORD, SENHA_MAGAZORD), json=corpo_midia)
        resultado = resposta.json()
        return resultado
    except Exception as erro:
        return {"sucesso": False, "mensagem": str(erro)}


def vincular_midia_produto(codigo_pai, codigo_filho, id_midia):
    url_vinculo  = f"{URL_MAGAZORD}/api/v2/site/produto/{codigo_pai}/derivacao/{codigo_filho}/midia"
    corpo_vinculo = {"midiaId": [id_midia]}
    try:
        resposta = requests.post(url_vinculo, auth=(TOKEN_MAGAZORD, SENHA_MAGAZORD), json=corpo_vinculo)
        return resposta.json()
    except Exception as erro:
        return {"sucesso": False, "mensagem": str(erro)}


def copiar_midias_para_categoria(arquivos: list, nome_categoria: str):
    def encontrar_pasta_categoria(nome, pasta_pai_id):
        resultado = servico_drive.files().list(
            q=f"'{pasta_pai_id}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false",
            fields="files(id, name)",
            pageSize=100
        ).execute()
        pastas = resultado.get("files", [])
        for pasta in pastas:
            if pasta["name"].strip().lower() == nome.strip().lower():
                return pasta["id"]
            sub_id = encontrar_pasta_categoria(nome, pasta["id"])
            if sub_id:
                return sub_id
        return None

    try:
        id_artana        = buscar_pasta_drive("ARTANA")
        id_midias        = buscar_pasta_drive("03_Mídias", id_artana)
        id_org_site      = buscar_pasta_drive("07_Organizados Site", id_midias)
        id_categoria     = encontrar_pasta_categoria(nome_categoria, id_org_site)

        if not id_categoria:
            return False

        for id_arquivo, nome_arquivo in arquivos:
            servico_drive.files().copy(
                fileId=id_arquivo,
                body={"name": nome_arquivo, "parents": [id_categoria]}
            ).execute()

        return True

    except Exception as erro:
        print(f"Erro ao copiar mídias: {erro}")
        return False


def obter_id_marca_magazord(nome_marca: str):
    url_marcas = f"{URL_MAGAZORD}/api/v2/site/marca"
    try:
        resposta = requests.get(url_marcas, auth=(TOKEN_MAGAZORD, SENHA_MAGAZORD))
        if resposta.status_code not in [200, 201]:
            return None
        itens = resposta.json().get("data", {}).get("items", [])
        return itens[0].get("id") if itens else None
    except Exception as erro:
        print(f"Erro ao buscar marca: {erro}")
        return None


def mapear_derivacoes(produto_info):
    tipo_variacao = produto_info.get("tipoVariacao", "N")
    if tipo_variacao == "N":
        return [3]
    derivacoes = set()
    for variacao in produto_info.get("variacoes", []):
        grade = variacao.get("variacao", {}).get("grade", {})
        if "cor" in grade:
            derivacoes.add(1)
        if "tamanho" in grade:
            derivacoes.add(2)
    return list(derivacoes) if derivacoes else [3]


def montar_derivacoes_filhos(grade):
    derivacoes = []
    if "cor" in grade:
        derivacoes.append({"derivacao": 1, "valor": grade["cor"]})
    if "tamanho" in grade:
        derivacoes.append({"derivacao": 2, "valor": grade["tamanho"]})
    if not derivacoes:
        derivacoes.append({"derivacao": 3, "valor": "Único"})
    return derivacoes


def buscar_categoria_magazord(nome_categoria: str):
    url_categorias = f"{URL_MAGAZORD}/api/v2/site/categoria"
    try:
        resposta = requests.get(
            url_categorias,
            auth=(TOKEN_MAGAZORD, SENHA_MAGAZORD),
            params={"nome": nome_categoria}
        )
        itens = resposta.json().get("data", {}).get("items", [])
        for item in itens:
            if item.get("nome") == nome_categoria and item.get("pai") is not None:
                return item.get("id")
        return None
    except Exception as erro:
        print(f"Erro ao buscar categoria: {erro}")
        return None


def processar_descricao(descricao: str, codigo_produto: str, largura_img="503", altura_img="381") -> str:
    if not descricao:
        return descricao

    descricao = descricao.replace("[", "").replace("]", "")
    descricao = html.unescape(descricao)

    soup = BeautifulSoup(descricao, "html.parser")

    for img in soup.find_all("img"):
        img["width"]  = largura_img
        img["height"] = altura_img

    padrao_youtube = re.compile(r"https?://(?:www\.)?youtube\.com/shorts/([A-Za-z0-9_-]+)")
    for node_texto in soup.find_all(text=True):
        if padrao_youtube.search(node_texto):
            novo_html = padrao_youtube.sub(
                lambda m: f'<p><iframe src="https://www.youtube.com/embed/{m.group(1)}" width="349" height="287"></iframe></p>',
                str(node_texto)
            )
            node_texto.replace_with(BeautifulSoup(novo_html, "html.parser"))

    return str(soup)


if __name__ == "__main__":
    app.run(debug=True)
