import makeWASocket, {
  DisconnectReason,
  fetchLatestBaileysVersion,
  useMultiFileAuthState,
} from "@whiskeysockets/baileys";
import qrcode from "qrcode-terminal";
import fs from "node:fs/promises";
import path from "node:path";

const FLASK_INGEST_URL = process.env.FLASK_INGEST_URL || "http://127.0.0.1:8000/ingest/companion";
const AUTH_DIR = process.env.BAILEYS_AUTH_DIR || "auth_info";
const RAW_EVENTS_DIR = process.env.BAILEYS_RAW_EVENTS_DIR || path.join("..", "raw_events");

async function main() {
  const { state, saveCreds } = await useMultiFileAuthState(AUTH_DIR);
  const { version } = await fetchLatestBaileysVersion();

  const socket = makeWASocket({
    auth: state,
    browser: ["WhatsApp Phone Server", "Chrome", "1.0.0"],
    printQRInTerminal: false,
    version,
  });

  socket.ev.on("creds.update", saveCreds);

  socket.ev.on("connection.update", (update) => {
    const { connection, lastDisconnect, qr } = update;

    if (qr) {
      console.log("Scan this QR from WhatsApp > Linked devices:");
      qrcode.generate(qr, { small: true });
    }

    if (connection === "open") {
      console.log("Baileys companion bridge connected.");
    }

    if (connection === "close") {
      const statusCode = lastDisconnect?.error?.output?.statusCode;
      const shouldReconnect = statusCode !== DisconnectReason.loggedOut;
      console.log(`Connection closed. Reconnect: ${shouldReconnect}`);
      if (shouldReconnect) {
        main().catch((error) => console.error("Restart failed:", error));
      } else {
        console.log(`Logged out. Delete ${AUTH_DIR} and relink if needed.`);
      }
    }
  });

  socket.ev.on("messages.upsert", async ({ messages, type }) => {
    if (type !== "notify") {
      return;
    }

    for (const message of messages || []) {
      try {
        const rawPayloadPath = await saveRawMessage(message);
        const normalized = await normalizeMessage(socket, message, rawPayloadPath);
        if (!normalized) {
          continue;
        }
        await postToFlask(normalized);
        console.log(`Ingested ${normalized.message_type} message ${normalized.message_id}`);
      } catch (error) {
        console.error("Failed to ingest message:", error?.message || error);
      }
    }
  });
}

async function normalizeMessage(socket, message, rawPayloadPath) {
  const key = message.key || {};
  const content = unwrapEphemeral(message.message || {});
  const messageType = detectMessageType(content);

  if (!key.id || !key.remoteJid || messageType === "unknown") {
    return null;
  }

  const chatId = key.remoteJid;
  const isGroup = chatId.endsWith("@g.us");
  const senderId = isGroup ? key.participant : chatId;
  const chatName = await resolveChatName(socket, chatId);

  const normalized = {
    source: "baileys",
    chat_id: chatId,
    chat_name: chatName,
    is_group: isGroup,
    group_id: isGroup ? chatId : null,
    sender_id: senderId || null,
    sender_name: message.pushName || null,
    message_id: key.id,
    timestamp: toIsoTimestamp(message.messageTimestamp),
    message_type: messageType,
    text_body: extractTextBody(content, messageType),
    media_type: isMediaType(messageType) ? messageType : null,
    media_path: null,
    raw_payload_path: rawPayloadPath,
  };

  if (isMediaType(messageType)) {
    normalized.text_body = extractCaption(content, messageType);
    // Future hook: download media with Baileys downloadMediaMessage and set media_path.
  }

  return normalized;
}

function unwrapEphemeral(content) {
  return (
    content.ephemeralMessage?.message ||
    content.viewOnceMessage?.message ||
    content.viewOnceMessageV2?.message ||
    content
  );
}

function detectMessageType(content) {
  if (content.conversation || content.extendedTextMessage) return "text";
  if (content.imageMessage) return "image";
  if (content.audioMessage) return "audio";
  if (content.videoMessage) return "video";
  if (content.documentMessage) return "document";
  if (content.stickerMessage) return "sticker";
  return "unknown";
}

function extractTextBody(content, messageType) {
  if (messageType !== "text") return null;
  return content.conversation || content.extendedTextMessage?.text || null;
}

function extractCaption(content, messageType) {
  const map = {
    image: content.imageMessage,
    video: content.videoMessage,
    document: content.documentMessage,
  };
  return map[messageType]?.caption || null;
}

function isMediaType(messageType) {
  return ["image", "audio", "video", "document", "sticker"].includes(messageType);
}

async function resolveChatName(socket, chatId) {
  if (!chatId.endsWith("@g.us")) {
    return null;
  }

  try {
    const metadata = await socket.groupMetadata(chatId);
    return metadata?.subject || null;
  } catch {
    return null;
  }
}

function toIsoTimestamp(timestamp) {
  if (!timestamp) return new Date().toISOString();
  const seconds = Number(timestamp?.low || timestamp);
  if (!Number.isFinite(seconds)) return new Date().toISOString();
  return new Date(seconds * 1000).toISOString();
}

async function saveRawMessage(message) {
  const now = new Date();
  const year = String(now.getUTCFullYear());
  const month = String(now.getUTCMonth() + 1).padStart(2, "0");
  const day = String(now.getUTCDate()).padStart(2, "0");
  const folder = path.join(RAW_EVENTS_DIR, "baileys", year, month, day);
  await fs.mkdir(folder, { recursive: true });

  const filename = `${now.toISOString().replace(/[:.]/g, "-")}--${message.key?.id || "unknown"}.json`;
  const filePath = path.join(folder, filename);
  await fs.writeFile(filePath, JSON.stringify(message, null, 2), "utf8");
  return filePath;
}

async function postToFlask(payload) {
  const response = await fetch(FLASK_INGEST_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const body = await response.text();
    throw new Error(`Flask ingest failed ${response.status}: ${body}`);
  }
}

main().catch((error) => {
  console.error("Bridge crashed:", error);
  process.exitCode = 1;
});
