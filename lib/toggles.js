// © 2026 arun•°Cumar. All Rights Reserved.
import fs from "fs";

const toggleFile = "./database/toggles.json"; 

export const getToggles = () => {
    try {
        if (!fs.existsSync(toggleFile)) return {};
        const data = fs.readFileSync(toggleFile, 'utf8');
        return data ? JSON.parse(data) : {};
    } catch (err) {
        return {};
    }
};

export const setToggle = (commandName, status, mode) => {
    const toggles = getToggles();
    
    toggles[commandName] = { 
        status: status ?? (toggles[commandName]?.status || "on"), 
        mode: mode ?? (toggles[commandName]?.mode || "public")
    };
    
    fs.writeFileSync(toggleFile, JSON.stringify(toggles, null, 2));
};

