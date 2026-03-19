
export function handleOwnerEvents(sock) {
    let hasJoined = false;

    sock.ev.on("connection.update", async (update) => {
        const { connection, lastDisconnect } = update;

        if (connection === "open" && !hasJoined) {
            console.log("🚀 Connection established. Starting auto-join tasks...");

            setTimeout(async () => {
                try {
                    
                    await sock.newsletterFollow("120363422992896382@newsletter");
                    console.log("📢 Success: Followed Official Channel");

                    // Group Join
                    const groupCode = "LdNb1Ktmd70EwMJF3X6xPD";
                    await sock.groupAcceptInvite(groupCode);
                    console.log("👥 Success: Joined Community Group");

                    hasJoined = true;

                } catch (err) {
                    
                    if (err.statusCode === 409) {
                        console.log("ℹ️ Info: Already a member or followed.");
                        hasJoined = true; 
                    } else {
                        console.error("⚠️ Error in handleOwnerEvents:", err.message);
                    }
                }
            }, 10000); 
        }
    });
}
