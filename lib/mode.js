import config from "../config.js";

export const checkMode = (sender, toggles) => {
    const isOwner = config.OWNER_NUMBER.includes(sender.split('@')[0]);
    const currentMode = toggles.global?.mode || "public";
    
    if (currentMode === "private" && !isOwner) {
        return false; // Permission denied
    }
    return true; // Permission granted
};
