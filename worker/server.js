const express = require("express");
const fs = require("fs");
const path = require("path");

const app = express();
const PORT = 8083;

// Caminho do JSON gerado pelo worker de saída
const SAIDA_PATH = "/home/roteiro_ds/autotrader-saida-posicional/data/saida_posicional.json";

// --------- ROTA DE API: /api/saida-posicional ---------
app.get("/api/saida-posicional", (req, res) => {
  try {
    if (!fs.existsSync(SAIDA_PATH)) {
      return res.json({ posicional: [], ultima_atualizacao: null });
    }

    const raw = fs.readFileSync(SAIDA_PATH, "utf8");
    let data = JSON.parse(raw);

    if (!data || typeof data !== "object") {
      data = { posicional: [], ultima_atualizacao: null };
    }
    if (!Array.isArray(data.posicional)) {
      data.posicional = [];
    }

    return res.json(data);
  } catch (err) {
    console.error("[ERRO] Lendo saida_posicional.json:", err);
    return res.status(500).json({ erro: "Falha ao ler dados de saída" });
  }
});

// --------- ARQUIVOS ESTÁTICOS (página do painel) ---------
const publicDir = path.join(__dirname, "public");
app.use(express.static(publicDir));

// Página principal na raiz "/"
app.get("/", (req, res) => {
  res.sendFile(path.join(publicDir, "index.html"));
});

// --------- INICIAR SERVIDOR ---------
app.listen(PORT, "0.0.0.0", () => {
  console.log(`Servidor Saída Posicional rodando em http://0.0.0.0:${PORT}`);
});
