import fs from 'fs';

export default async (sock, msg, args) => {
    const from = msg.key.remoteJid;
    const isOwner = msg.key.fromMe; 

    if (!isOwner) return sock.sendMessage(from, { text: "❌ Owner only!" });

    const dbPath = './database/mode.json';
    const db = JSON.parse(fs.readFileSync(dbPath, 'utf-8'));

    const action = args[0]?.toLowerCase();

    if (action === 'public') {
        db.isPublic = true;
        fs.writeFileSync(dbPath, JSON.stringify(db, null, 2));
        await sock.sendMessage(from, { text: "🔓 *Mode:* Public enabled" });
    } 
    else if (action === 'private') {
        db.isPublic = false;
        fs.writeFileSync(dbPath, JSON.stringify(db, null, 2));
        await sock.sendMessage(from, { text: "🔒 *Mode:* Private enabled" });
    } 
    else {
        await sock.sendMessage(from, { text: "❓ Usage: *.mode public* or *.mode private*" });
    }
};
