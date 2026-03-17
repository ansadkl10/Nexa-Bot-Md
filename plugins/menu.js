import { promises as fs } from 'fs';
import path from 'path';

export default async (sock, msg, { args, prefix }) => {
    try {
        const imagePath = './nexa.jpg'; 
        const pluginsDir = path.join(process.cwd(), 'plugins');
        const files = await fs.readdir(pluginsDir);
        const commands = files
            .filter(file => file.endsWith('.js'))
            .map(file => file.replace('.js', ''));

        let menuText = `✨ *NEXA-BOT MD MENU* ✨\n\n`;
        menuText += `📅 *Date:* ${new Date().toLocaleDateString()}\n`;
        menuText += `🤖 *Prefix:* [ ${prefix} ]\n`;
        menuText += `📂 *Total Plugins:* ${commands.length}\n\n`;
        menuText += `*📜 COMMAND LIST:*\n`;

        commands.forEach((cmd, index) => {
            menuText += `${index + 1}. ${prefix}${cmd}\n`;
        });

        menuText += `\n> Powered by Nexa-Bot`;
      
        await sock.sendMessage(msg.key.remoteJid, {
            image: { url: imagePath },
            caption: menuText
        }, { quoted: msg });

    } catch (error) {
        console.error(error);
        await sock.sendMessage(msg.key.remoteJid, { text: "Error" });
    }
};
