import os
import pickle
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

ESCOPOS = ["https://www.googleapis.com/auth/drive"]

def conectar_drive():
    credenciais = None

    if os.path.exists("token.pickle"):
        with open("token.pickle", "rb") as arquivo_token:
            credenciais = pickle.load(arquivo_token)

    if not credenciais or not credenciais.valid:
        if credenciais and credenciais.expired and credenciais.refresh_token:
            credenciais.refresh(Request())
        else:
            fluxo = InstalledAppFlow.from_client_secrets_file("credentials.json", ESCOPOS)
            credenciais = fluxo.run_local_server(port=0)

        with open("token.pickle", "wb") as arquivo_token:
            pickle.dump(credenciais, arquivo_token)

    servico = build("drive", "v3", credentials=credenciais)
    return servico
