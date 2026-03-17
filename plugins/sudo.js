import fs from 'fs';
import config from '../config.js';

const sudoFile = './media/sudos.json';

const getSudos = () => {
    if (fs.existsSync(sudoFile)) {
        return JSON.parse(fs.readFileSync(sudoFile));
    }
    return config.OWNER_NUMBER || [];
};

const saveSudos = (sudos) => {
    fs.writeFileSync(sudoFile, JSON.stringify(sudos, null, 2));
};

export default async (sock, msg, args, extra) => {
    const chat = msg.key.remoteJid;
    const sender = msg.key.participant || msg.key.remoteJid;
    const senderNum = sender.split('@')[0];
    
    const sudos = getSudos();
    const isOwner = sudos.includes(senderNum);
    
    const sub = args[0]?.toLowerCase();

    if (!sub) {
        return await sock.sendMessage(chat, {
            text: `╭━━〔 🛡️ *SUDO MANAGER* 〕━━╮
┃
┃  *.setsudo <number>*
┃    Add owner
┃
┃  *.delsudo <number>*
┃    Remove owner
┃
┃  *.getsudo*
┃    List all owners
┃
╰━━━━━━━━━━━━━━━━━━━╯`
        }, { quoted: msg });
    }

    if (!isOwner) {
        return await sock.sendMessage(chat, {
            text: '❌ Only *sudos/owners* can manage the sudo list.'
        }, { quoted: msg });
    }

    if (sub === 'setsudo' || sub === 'add') {
        const num = args[1];
        if (!num) return await sock.sendMessage(chat, { text: '❌ Provide number: `.setsudo 91xxxxxxxxxx`' }, { quoted: msg });
        
        const cleanNum = num.replace(/[^0-9]/g, '');
        
        if (sudos.includes(cleanNum)) {
            return await sock.sendMessage(chat, { text: `⚠️ *${cleanNum}* is already an owner.` }, { quoted: msg });
        }
        
        sudos.push(cleanNum);
        saveSudos(sudos);
        await sock.sendMessage(chat, { text: `✅ *${cleanNum}* has been added as an *owner*.` }, { quoted: msg });
    }

    else if (sub === 'delsudo' || sub === 'del' || sub === 'remove') {
        const num = args[1];
        if (!num) return await sock.sendMessage(chat, { text: '❌ Provide number: `.delsudo 91xxxxxxxxxx`' }, { quoted: msg });
        
        const cleanNum = num.replace(/[^0-9]/g, '');
        
        if (!sudos.includes(cleanNum)) {
            return await sock.sendMessage(chat, { text: `⚠️ *${cleanNum}* is not in the owner list.` }, { quoted: msg });
        }
        
        const index = sudos.indexOf(cleanNum);
        sudos.splice(index, 1);
        saveSudos(sudos);
        await sock.sendMessage(chat, { text: `✅ *${cleanNum}* has been removed from owners.` }, { quoted: msg });
    }

    else if (sub === 'getsudo' || sub === 'list') {
        if (!sudos.length) {
            return await sock.sendMessage(chat, { text: '❌ No owners found.' }, { quoted: msg });
        }
        
        const list = sudos.map((n, i) => `${i + 1}. ${n}`).join('\n');
        await sock.sendMessage(chat, {
            text: `👥 *SUDO LIST* (${sudos.length})\n\n${list}`
        }, { quoted: msg });
    }

    else {
        await sock.sendMessage(chat, { text: '❌ Unknown sub-command. Use `.sudo` for help.' }, { quoted: msg });
    }
};
