import fs from "fs";
import path from "path";
import { pathToFileURL } from 'url';
import config from "./config.js";

export default async (sock, chatUpdate) => {
    try {
        const msg = chatUpdate.messages[0];
        if (!msg.message || msg.key.remoteJid === 'status@broadcast') return;

        const from = msg.key.remoteJid;
        const body = (msg.message.conversation || msg.message.extendedTextMessage?.text || "").trim();
        const isCmd = body.startsWith(config.PREFIX);
        const commandName = isCmd ? body.slice(config.PREFIX.length).split(" ")[0].toLowerCase() : "";
        const args = body.trim().split(/ +/).slice(1);

        if (isCmd) {
            const commandPath = path.join(process.cwd(), "plugins", `${commandName}.js`);

            if (fs.existsSync(commandPath)) {
                await sock.sendPresenceUpdate('composing', from);
                const moduleUrl = pathToFileURL(commandPath).href + `?update=${Date.now()}`;
                const commandModule = await import(moduleUrl);
                
                const handler = commandModule.default || commandModule.run;
                if (handler) await handler(sock, msg, args);
            }
        }
    } catch (err) {
        console.error("Message Error:", err);
    }
};
