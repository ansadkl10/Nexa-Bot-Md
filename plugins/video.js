import axios from 'axios';

export default async (sock, msg, args, extra) => {
    const chat = msg.key.remoteJid;
    const url = args.join(' ');
    
    if (!url) {
        return await sock.sendMessage(chat, {
            text: `❌ Provide YouTube URL\n\nUsage: *.video* <youtube_url>\n\nExamples:\n.video https://youtu.be/ti5MaCUuCe4\n.video https://www.youtube.com/watch?v=ABC123`
        }, { quoted: msg });
    }
    
    if (!url.includes('youtube.com') && !url.includes('youtu.be')) {
        return await sock.sendMessage(chat, {
            text: '❌ Invalid YouTube URL. Must be from youtube.com or youtu.be'
        }, { quoted: msg });
    }
    
    await sock.sendMessage(chat, { react: { text: '▶️', key: msg.key } });
    
    try {
        const apiUrl = `https://api.sparky.biz.id/api/downloader/ytv?url=${encodeURIComponent(url)}`;
        const response = await axios.get(apiUrl, { timeout: 15000 });
        
        if (!response.data.status || !response.data.data) {
            return await sock.sendMessage(chat, {
                text: '❌ Failed to fetch video. The video may be:\n• Private\n• Deleted\n• Not available in your region'
            }, { quoted: msg });
        }
        
        const data = response.data.data;
        const title = data.title || 'Unknown Title';
        const downloadUrl = data.url;
        
        const info = `▶️ *YOUTUBE VIDEO*\n\n📌 *Title:* ${title}\n\n📥 *Download Link:*\n${downloadUrl}`;
        
        await sock.sendMessage(chat, {
            text: info
        }, { quoted: msg });
        
    } catch (e) {
        console.error('YouTube Downloader Error:', e.message);
        await sock.sendMessage(chat, {
            text: '❌ Download failed.\n\nPossible reasons:\n• Invalid URL\n• Video not found\n• Server is down\n\nTry again later!'
        }, { quoted: msg });
    }
};
