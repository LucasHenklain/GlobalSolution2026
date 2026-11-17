"""Segurança do app: senha (bcrypt), telefone cifrado (Fernet), máscara, limite de tentativas de login e tokens."""

from __future__ import annotations

import hmac
import re
import secrets
import time
from functools import lru_cache

import bcrypt
from cryptography.fernet import Fernet, InvalidToken

from comum.config import Config, carregar_config, segredo_local

MAX_FALHAS_LOGIN = 5
JANELA_BLOQUEIO_S = 15 * 60
LIMITE_BYTES_SENHA = 72  # o bcrypt só considera os primeiros 72 bytes


# ---------- senha ----------


def _custo_bcrypt() -> int:
    """Custo alto em dev/prod (ataque de força bruta fica caro); custo mínimo só nos testes, para rodarem rápido."""
    return 4 if carregar_config().ambiente == "teste" else 12


def problemas_da_senha(senha: str) -> str | None:
    """Devolve a mensagem de erro da senha fraca, ou None se ela serve."""
    if len(senha) < 8:
        return "A senha precisa ter pelo menos 8 caracteres."
    if len(senha.encode("utf-8")) > LIMITE_BYTES_SENHA:
        return "A senha é longa demais (use até 72 caracteres)."
    if not re.search(r"[A-Za-zÀ-ÿ]", senha) or not re.search(r"\d", senha):
        return "A senha precisa ter pelo menos uma letra e um número."
    return None


def gerar_hash_senha(senha: str) -> str:
    """Nunca guardamos a senha: só o hash bcrypt (com sal aleatório embutido)."""
    return bcrypt.hashpw(senha.encode("utf-8"), bcrypt.gensalt(rounds=_custo_bcrypt())).decode("ascii")


@lru_cache(maxsize=2)
def _hash_de_mentira(custo: int) -> str:
    return bcrypt.hashpw(secrets.token_bytes(16), bcrypt.gensalt(rounds=custo)).decode("ascii")


def conferir_senha(senha: str, senha_hash: str | None) -> bool:
    """Confere a senha. Sem usuário, usa um hash de mentira: o tempo de resposta não revela se o e-mail existe."""
    senha_bytes = senha.encode("utf-8")
    if len(senha_bytes) > LIMITE_BYTES_SENHA:
        return False
    alvo = senha_hash or _hash_de_mentira(_custo_bcrypt())
    try:
        confere = bcrypt.checkpw(senha_bytes, alvo.encode("ascii"))
    except ValueError:
        return False
    return confere and senha_hash is not None


# ---------- telefone: cifrado em repouso, mascarado na tela ----------


def chave_de_sessao(cfg: Config) -> str:
    """Chave que assina o cookie de sessão; em dev/teste é gerada e guardada em var/ (fora do Git)."""
    return cfg.secret_key or segredo_local("secret_key")


@lru_cache(maxsize=4)
def _cifra(chave: str) -> Fernet:
    return Fernet(chave.encode("ascii"))


def _cifra_atual() -> Fernet:
    cfg = carregar_config()
    chave = cfg.chave_dados or segredo_local("chave_dados", gerador=lambda: Fernet.generate_key().decode())
    return _cifra(chave)


def normalizar_telefone(texto: str) -> str | None:
    """Aceita '(11) 91234-5678', '11912345678' ou '+55 11 91234-5678'; devolve só os 11 dígitos ou None se inválido."""
    digitos = re.sub(r"\D", "", texto)
    if len(digitos) == 13 and digitos.startswith("55"):
        digitos = digitos[2:]
    if re.fullmatch(r"[1-9]\d9\d{8}", digitos):
        return digitos
    return None


def cifrar_telefone(digitos: str) -> str:
    """O banco só recebe o telefone cifrado: quem copiar o arquivo .db não lê os números."""
    return _cifra_atual().encrypt(digitos.encode("ascii")).decode("ascii")


def decifrar_telefone(cifrado: str | None) -> str | None:
    """Devolve os dígitos, ou None se não há telefone ou a chave mudou."""
    if not cifrado:
        return None
    try:
        return _cifra_atual().decrypt(cifrado.encode("ascii")).decode("ascii")
    except InvalidToken:
        return None


def mascarar_telefone(digitos: str | None) -> str:
    """(11) *****-1234: o suficiente para a pessoa reconhecer o próprio número, sem expor."""
    if not digitos or len(digitos) < 6:
        return ""
    return f"({digitos[:2]}) *****-{digitos[-4:]}"


# ---------- limite de tentativas de login ----------


class LimiteLogin:
    """Conta falhas por e-mail+IP em memória; depois de 5 falhas bloqueia novas tentativas por 15 minutos."""

    def __init__(self, max_falhas: int = MAX_FALHAS_LOGIN, janela_s: int = JANELA_BLOQUEIO_S) -> None:
        self.max_falhas = max_falhas
        self.janela_s = janela_s
        self._falhas: dict[str, list[float]] = {}

    def _recentes(self, chave: str) -> list[float]:
        limite = time.monotonic() - self.janela_s
        return [t for t in self._falhas.get(chave, []) if t > limite]

    def bloqueado(self, chave: str) -> bool:
        return len(self._recentes(chave)) >= self.max_falhas

    def registrar_falha(self, chave: str) -> None:
        self._falhas[chave] = [*self._recentes(chave), time.monotonic()]
        if len(self._falhas) > 10_000:  # não deixa a memória crescer sem fim sob ataque
            self._falhas = {c: f for c in list(self._falhas) if (f := self._recentes(c))}

    def limpar(self, chave: str) -> None:
        self._falhas.pop(chave, None)


# ---------- CSRF e token interno ----------


def novo_token() -> str:
    return secrets.token_urlsafe(32)


def iguais(a: str, b: str) -> bool:
    """Comparação em tempo constante: não vaza, pelo tempo de resposta, quantos caracteres estão certos."""
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))
