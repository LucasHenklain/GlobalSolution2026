"""Banco do app (SQLite da biblioteca padrão). Todo SQL fica aqui, sempre parametrizado (nunca montado com texto)."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

ESQUEMA = """
CREATE TABLE IF NOT EXISTS usuarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    senha_hash TEXT NOT NULL,
    telefone_cifrado TEXT,
    estacao_id TEXT,
    papel TEXT NOT NULL DEFAULT 'morador' CHECK (papel IN ('morador', 'agente')),
    receber_sms INTEGER NOT NULL DEFAULT 1,
    fonte_grande INTEGER NOT NULL DEFAULT 0,
    alto_contraste INTEGER NOT NULL DEFAULT 0,
    versao_sessao INTEGER NOT NULL DEFAULT 1,
    consentimento_em TEXT NOT NULL,
    criado_em TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS situacoes (
    estacao_id TEXT PRIMARY KEY,
    atualizado_em TEXT NOT NULL,
    recebido_em TEXT NOT NULL,
    nivel_cm REAL NOT NULL,
    nivel_pct_cota REAL NOT NULL,
    chuva_1h REAL NOT NULL,
    chuva_24h REAL,
    delta_nivel_30min REAL,
    prob_transbordo_60min REAL,
    nivel_risco TEXT NOT NULL,
    estado_regra TEXT,
    bateria_pct REAL,
    origem TEXT,
    serie_json TEXT NOT NULL DEFAULT '[]'
);
CREATE TABLE IF NOT EXISTS alertas (
    alerta_id TEXT PRIMARY KEY,
    estacao_id TEXT NOT NULL,
    emitido_em TEXT NOT NULL,
    recebido_em TEXT NOT NULL,
    nivel_risco TEXT NOT NULL,
    prob REAL,
    nivel_cm REAL,
    chuva_1h REAL,
    titulo TEXT NOT NULL,
    mensagem TEXT NOT NULL,
    mensagem_sms TEXT NOT NULL,
    motivo_json TEXT NOT NULL DEFAULT '[]',
    orientacoes_json TEXT NOT NULL DEFAULT '[]',
    origem_decisao TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS ocorrencias (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario_id INTEGER REFERENCES usuarios(id) ON DELETE SET NULL,
    estacao_id TEXT NOT NULL,
    tipo TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'aberta',
    descricao TEXT NOT NULL DEFAULT '',
    criada_em TEXT NOT NULL,
    atualizada_em TEXT NOT NULL,
    encerrada_em TEXT
);
CREATE TABLE IF NOT EXISTS sms_saida (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    alerta_id TEXT NOT NULL REFERENCES alertas(alerta_id),
    usuario_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    telefone_mascarado TEXT NOT NULL,
    mensagem TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'simulado',
    criado_em TEXT NOT NULL,
    UNIQUE (alerta_id, usuario_id)
);
CREATE TABLE IF NOT EXISTS comandos_sirene (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    estacao_id TEXT NOT NULL,
    acao TEXT NOT NULL,
    nivel TEXT NOT NULL,
    segundos INTEGER NOT NULL,
    entregue INTEGER NOT NULL,
    enviado_em TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_alertas_estacao ON alertas (estacao_id, emitido_em);
CREATE INDEX IF NOT EXISTS idx_ocorrencias_usuario ON ocorrencias (usuario_id);
"""

TEXTO_REMOVIDO = "[descrição removida a pedido do titular]"


def agora_iso() -> str:
    """Hora atual em UTC no formato do contrato (ISO 8601 com Z)."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def conectar(caminho: Path) -> sqlite3.Connection:
    """Abre uma conexão por requisição; as linhas voltam como dicionário (linha['coluna'])."""
    caminho.parent.mkdir(parents=True, exist_ok=True)
    # check_same_thread=False: o FastAPI pode abrir e usar a conexão em threads diferentes da mesma requisição.
    con = sqlite3.connect(caminho, timeout=10, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def criar_tabelas(caminho: Path) -> None:
    """Cria o banco e as tabelas se ainda não existirem (pode rodar a cada subida do app)."""
    con = conectar(caminho)
    try:
        con.executescript(ESQUEMA)
        con.execute("PRAGMA journal_mode = WAL")  # leitura não trava escrita (pipeline e telas ao mesmo tempo)
    finally:
        con.close()


# ---------- usuários ----------


def criar_usuario(
    con: sqlite3.Connection,
    nome: str,
    email: str,
    senha_hash: str,
    telefone_cifrado: str | None,
    estacao_id: str | None,
    papel: str = "morador",
) -> int:
    """Grava o cadastro; a data do consentimento LGPD fica registrada junto."""
    agora = agora_iso()
    with con:
        cursor = con.execute(
            "INSERT INTO usuarios"
            " (nome, email, senha_hash, telefone_cifrado, estacao_id, papel, consentimento_em, criado_em)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (nome, email, senha_hash, telefone_cifrado, estacao_id, papel, agora, agora),
        )
    return int(cursor.lastrowid)


def usuario_por_email(con: sqlite3.Connection, email: str) -> sqlite3.Row | None:
    return con.execute("SELECT * FROM usuarios WHERE email = ?", (email,)).fetchone()


def usuario_por_id(con: sqlite3.Connection, usuario_id: int) -> sqlite3.Row | None:
    return con.execute("SELECT * FROM usuarios WHERE id = ?", (usuario_id,)).fetchone()


def atualizar_perfil(con: sqlite3.Connection, usuario_id: int, dados: dict) -> None:
    """Atualiza só os campos que o morador pode editar (as colunas são fixas, não vêm do formulário)."""
    with con:
        con.execute(
            "UPDATE usuarios SET nome = ?, telefone_cifrado = ?, estacao_id = ?, receber_sms = ?,"
            " fonte_grande = ?, alto_contraste = ? WHERE id = ?",
            (
                dados["nome"],
                dados["telefone_cifrado"],
                dados["estacao_id"],
                int(dados["receber_sms"]),
                int(dados["fonte_grande"]),
                int(dados["alto_contraste"]),
                usuario_id,
            ),
        )


def encerrar_sessoes(con: sqlite3.Connection, usuario_id: int) -> None:
    """Sobe a versão da sessão: cookies antigos desse usuário deixam de valer (usado ao sair)."""
    with con:
        con.execute("UPDATE usuarios SET versao_sessao = versao_sessao + 1 WHERE id = ?", (usuario_id,))


def excluir_usuario(con: sqlite3.Connection, usuario_id: int) -> None:
    """LGPD: apaga os dados pessoais. As ocorrências ficam anônimas e sem o texto livre (pode conter dado pessoal)."""
    with con:
        con.execute(
            "UPDATE ocorrencias SET descricao = ?, usuario_id = NULL WHERE usuario_id = ?", (TEXTO_REMOVIDO, usuario_id)
        )
        con.execute("DELETE FROM sms_saida WHERE usuario_id = ?", (usuario_id,))
        con.execute("DELETE FROM usuarios WHERE id = ?", (usuario_id,))


# ---------- situação das estações ----------

_COLUNAS_SITUACAO = (
    "estacao_id",
    "atualizado_em",
    "nivel_cm",
    "nivel_pct_cota",
    "chuva_1h",
    "chuva_24h",
    "delta_nivel_30min",
    "prob_transbordo_60min",
    "nivel_risco",
    "estado_regra",
    "bateria_pct",
    "origem",
)


def salvar_situacoes(con: sqlite3.Connection, situacoes: list[dict]) -> int:
    """Substitui a situação atual de cada estação recebida (uma linha por estação)."""
    agora = agora_iso()
    with con:
        for s in situacoes:
            valores = [s.get(c) for c in _COLUNAS_SITUACAO]
            con.execute(
                "INSERT OR REPLACE INTO situacoes (estacao_id, atualizado_em, nivel_cm, nivel_pct_cota, chuva_1h,"
                " chuva_24h, delta_nivel_30min, prob_transbordo_60min, nivel_risco, estado_regra, bateria_pct, origem,"
                " serie_json, recebido_em) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (*valores, json.dumps(s.get("serie", [])), agora),
            )
    return len(situacoes)


def _situacao(linha: sqlite3.Row) -> dict:
    dados = dict(linha)
    dados["serie"] = json.loads(dados.pop("serie_json"))
    return dados


def listar_situacoes(con: sqlite3.Connection) -> dict[str, dict]:
    """Devolve {estacao_id: situação} com o último estado conhecido de cada estação."""
    linhas = con.execute("SELECT * FROM situacoes").fetchall()
    return {linha["estacao_id"]: _situacao(linha) for linha in linhas}


def buscar_situacao(con: sqlite3.Connection, estacao_id: str) -> dict | None:
    linha = con.execute("SELECT * FROM situacoes WHERE estacao_id = ?", (estacao_id,)).fetchone()
    return _situacao(linha) if linha else None


def ultima_situacao_em(con: sqlite3.Connection) -> str | None:
    """Usado pelo /health: mostra se o pipeline está entregando dados."""
    return con.execute("SELECT MAX(atualizado_em) FROM situacoes").fetchone()[0]


# ---------- alertas e SMS ----------


def salvar_alerta(con: sqlite3.Connection, alerta: dict, destinatarios: list[tuple[int, str]]) -> bool:
    """Grava o alerta e os SMS numa única transação. Devolve False se o alerta já existia (idempotência)."""
    agora = agora_iso()
    with con:
        cursor = con.execute(
            "INSERT OR IGNORE INTO alertas"
            " (alerta_id, estacao_id, emitido_em, recebido_em, nivel_risco, prob, nivel_cm,"
            " chuva_1h, titulo, mensagem, mensagem_sms, motivo_json, orientacoes_json, origem_decisao)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                alerta["alerta_id"],
                alerta["estacao_id"],
                alerta["emitido_em"],
                agora,
                alerta["nivel_risco"],
                alerta.get("prob"),
                alerta.get("nivel_cm"),
                alerta.get("chuva_1h"),
                alerta["titulo"],
                alerta["mensagem"],
                alerta["mensagem_sms"],
                json.dumps(alerta.get("motivo", []), ensure_ascii=False),
                json.dumps(alerta.get("orientacoes", []), ensure_ascii=False),
                alerta["origem_decisao"],
            ),
        )
        if cursor.rowcount == 0:
            return False
        con.executemany(
            "INSERT OR IGNORE INTO sms_saida (alerta_id, usuario_id, telefone_mascarado, mensagem, criado_em)"
            " VALUES (?, ?, ?, ?, ?)",
            [(alerta["alerta_id"], uid, mascarado, alerta["mensagem_sms"], agora) for uid, mascarado in destinatarios],
        )
    return True


def _alerta(linha: sqlite3.Row) -> dict:
    dados = dict(linha)
    dados["motivo"] = json.loads(dados.pop("motivo_json"))
    dados["orientacoes"] = json.loads(dados.pop("orientacoes_json"))
    return dados


def listar_alertas(con: sqlite3.Connection, estacao_id: str | None = None, limite: int = 50) -> list[dict]:
    """Alertas mais recentes primeiro; com estacao_id, só os daquela área."""
    if estacao_id:
        sql = "SELECT * FROM alertas WHERE estacao_id = ? ORDER BY emitido_em DESC, recebido_em DESC LIMIT ?"
        linhas = con.execute(sql, (estacao_id, limite)).fetchall()
    else:
        linhas = con.execute(
            "SELECT * FROM alertas ORDER BY emitido_em DESC, recebido_em DESC LIMIT ?", (limite,)
        ).fetchall()
    return [_alerta(linha) for linha in linhas]


def buscar_alerta(con: sqlite3.Connection, alerta_id: str) -> dict | None:
    linha = con.execute("SELECT * FROM alertas WHERE alerta_id = ?", (alerta_id,)).fetchone()
    return _alerta(linha) if linha else None


def moradores_para_sms(con: sqlite3.Connection, estacao_id: str) -> list[sqlite3.Row]:
    """Moradores da área que aceitaram SMS e informaram telefone."""
    return con.execute(
        "SELECT id, telefone_cifrado FROM usuarios"
        " WHERE estacao_id = ? AND receber_sms = 1 AND telefone_cifrado IS NOT NULL AND papel = 'morador'",
        (estacao_id,),
    ).fetchall()


def listar_sms(con: sqlite3.Connection, limite: int = 30) -> list[sqlite3.Row]:
    """Caixa de saída para o agente: só telefone mascarado, sem nome nem e-mail."""
    return con.execute(
        "SELECT s.id, s.alerta_id, s.telefone_mascarado, s.mensagem, s.status, s.criado_em, a.estacao_id"
        " FROM sms_saida s JOIN alertas a ON a.alerta_id = s.alerta_id ORDER BY s.id DESC LIMIT ?",
        (limite,),
    ).fetchall()


def sms_do_usuario(con: sqlite3.Connection, usuario_id: int) -> list[sqlite3.Row]:
    return con.execute(
        "SELECT alerta_id, mensagem, criado_em FROM sms_saida WHERE usuario_id = ? ORDER BY id", (usuario_id,)
    ).fetchall()


# ---------- ocorrências ----------


def criar_ocorrencia(con: sqlite3.Connection, usuario_id: int, estacao_id: str, tipo: str, descricao: str) -> int:
    agora = agora_iso()
    with con:
        cursor = con.execute(
            "INSERT INTO ocorrencias (usuario_id, estacao_id, tipo, descricao, criada_em, atualizada_em)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (usuario_id, estacao_id, tipo, descricao, agora, agora),
        )
    return int(cursor.lastrowid)


def ocorrencias_do_usuario(con: sqlite3.Connection, usuario_id: int) -> list[sqlite3.Row]:
    """Controle por dono: o filtro por usuario_id é feito aqui, no banco."""
    return con.execute("SELECT * FROM ocorrencias WHERE usuario_id = ? ORDER BY id DESC", (usuario_id,)).fetchall()


def fila_ocorrencias(con: sqlite3.Connection, limite: int = 100) -> list[sqlite3.Row]:
    """Fila do agente: abertas primeiro, depois em atendimento, depois resolvidas; mais novas no topo."""
    return con.execute(
        "SELECT id, estacao_id, tipo, status, descricao, criada_em, atualizada_em, encerrada_em FROM ocorrencias"
        " ORDER BY CASE status WHEN 'aberta' THEN 0 WHEN 'em_atendimento' THEN 1 ELSE 2 END, id DESC LIMIT ?",
        (limite,),
    ).fetchall()


def mudar_status_ocorrencia(con: sqlite3.Connection, ocorrencia_id: int, status: str) -> bool:
    """Devolve False se a ocorrência não existe. 'resolvida' grava a data de encerramento."""
    agora = agora_iso()
    encerrada = agora if status == "resolvida" else None
    with con:
        cursor = con.execute(
            "UPDATE ocorrencias SET status = ?, atualizada_em = ?, encerrada_em = ? WHERE id = ?",
            (status, agora, encerrada, ocorrencia_id),
        )
    return cursor.rowcount == 1


def ocorrencias_desde(con: sqlite3.Connection, desde: str | None) -> list[dict]:
    """Extrato para o pipeline: sem usuario_id, nome, e-mail ou telefone."""
    linhas = con.execute(
        "SELECT id AS ocorrencia_id, estacao_id, tipo, status, descricao, criada_em, atualizada_em, encerrada_em"
        " FROM ocorrencias WHERE atualizada_em >= ? ORDER BY id",
        (desde or "",),
    ).fetchall()
    return [dict(linha) for linha in linhas]


# ---------- sirene ----------


def registrar_comando_sirene(con: sqlite3.Connection, comando: dict, estacao_id: str, entregue: bool) -> None:
    """Trilha de auditoria: todo acionamento manual fica registrado, entregue ou não."""
    with con:
        con.execute(
            "INSERT INTO comandos_sirene (estacao_id, acao, nivel, segundos, entregue, enviado_em)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (estacao_id, comando["acao"], comando["nivel"], comando["segundos"], int(entregue), agora_iso()),
        )


def listar_comandos_sirene(con: sqlite3.Connection, limite: int = 10) -> list[sqlite3.Row]:
    return con.execute("SELECT * FROM comandos_sirene ORDER BY id DESC LIMIT ?", (limite,)).fetchall()
