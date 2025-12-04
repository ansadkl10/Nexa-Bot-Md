import os
import re
import asyncio
from pyrogram import Client, filters
from pyrogram.enums import MessagesFilter, ChatType
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, Document, Video, Audio
from pyrogram.errors import UserNotParticipant, MessageNotModified
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
from typing import List, Dict, Any, Union
from fastapi import FastAPI, Request, Response
from contextlib import asynccontextmanager
from http import HTTPStatus
import uvicorn

# Load variables from the .env file
load_dotenv()

# --- GLOBAL STATUS FLAG ---
# Tracks whether indexing is currently running.
IS_INDEXING_RUNNING = False

# --- CONFIG VARIABLES ---
API_ID = int(os.environ.get("API_ID", 12345))
API_HASH = os.environ.get("API_HASH", "YOUR_API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN")
PRIVATE_FILE_STORE = int(os.environ.get("PRIVATE_FILE_STORE", -100)) # Channel ID where files are stored
LOG_CHANNEL = int(os.environ.get("LOG_CHANNEL", -100))
# User session string is mandatory to index the private channel
USER_SESSION_STRING = os.environ.get("USER_SESSION_STRING", None) 


# Admin list
ADMINS = []
admin_env = os.environ.get("ADMINS", "")
if admin_env:
    ADMINS = [int(admin.strip()) for admin in admin_env.split(',') if admin.strip().isdigit()]

DATABASE_URL = os.environ.get("DATABASE_URL", "mongodb://localhost:27017")
FORCE_SUB_CHANNEL = os.environ.get("FORCE_SUB_CHANNEL", None) # Force subscribe channel (e.g., @MyChannel)

# Webhook details
WEBHOOK_URL_BASE = os.environ.get("WEBHOOK_URL_BASE", None)
PORT = int(os.environ.get("PORT", 8080))
WEBHOOK_PATH = f"/{BOT_TOKEN}"

# --- MONGODB SETUP ---

class Database:
    """Handles database operations."""
    def __init__(self, uri: str, database_name: str):
        self._client = AsyncIOMotorClient(uri)
        self.db = self._client[database_name]
        self.files_col = self.db["files"]

    async def get_all_files(self) -> List[Dict[str, Any]]:
        """Returns all file entries as a list."""
        cursor = self.files_col.find({})
        return await cursor.to_list(length=None)

    async def find_one(self, query: Dict[str, Any]) -> Dict[str, Any] | None:
        return await self.files_col.find_one(query)

    async def update_one(self, query: Dict[str, Any], update: Dict[str, Any], upsert: bool = False):
        await self.files_col.update_one(query, update, upsert=upsert)

# Database instance
db = Database(DATABASE_URL, "AutoFilterBot")

# --- PYROGRAM CLIENT ---
class AutoFilterBot(Client):
    def __init__(self):
        super().__init__(
            "AutoFilterBot",
            api_id=API_ID,
            api_hash=API_HASH,
            bot_token=BOT_TOKEN,
            plugins=dict(root="plugins"),
            sleep_threshold=30
        )

# --- BOT INSTANCE (GLOBAL PYROGRAM CLIENT) ---
app = AutoFilterBot()

# --- HELPERS ---

async def is_subscribed(client, user_id, max_retries=2, delay=1):
    """
    Checks if the user is a member of the force subscribe channel, with a retry mechanism
    to mitigate Telegram membership cache delays.
    """
    if not FORCE_SUB_CHANNEL:
        return True
    
    for attempt in range(max_retries):
        try:
            # Check if the user is a member of the channel via the bot
            member = await client.get_chat_member(FORCE_SUB_CHANNEL, user_id) 
            if member.status in ["member", "administrator", "creator"]:
                return True
            # If not a member/creator/admin, break and return False immediately
            return False 
        except UserNotParticipant:
            print("DEBUG: User is NOT a member of the force sub channel.")
            return False
        except Exception as e:
            print(f"Error checking subscription (Attempt {attempt+1}): {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(delay) # Wait before retrying
            
    return False # If all retries fail, assume not subscribed to show the button

async def get_file_details(query: str):
    """
    Searches for file details in the database using advanced tokenization and Regex
    to ensure filtering works regardless of search order or partial queries.
    """
    
    print(f"DEBUG: Search query: '{query}'")

    # 1. Prepare for Advanced Search: Tokenize the query
    # Split query by non-word characters and ensure words are longer than 1 char
    words = [word.strip() for word in re.split(r'\W+', query) if len(word.strip()) > 1]
    
    # --- Search Logic 1: All tokens must be present (Order agnostic) ---
    all_word_conditions = []
    if words:
        for word in words:
            word_regex = re.escape(word)
            # Each word must be present in title or caption (using word boundary \b for accuracy)
            all_word_conditions.append({
                "$or": [
                    {"title": {"$regex": f".*\\b{word_regex}\\b.*", "$options": "i"}},
                    {"caption": {"$regex": f".*\\b{word_regex}\\b.*", "$options": "i"}}
                ]
            })

    # --- Search Logic 2: Simple Phrase Match (Fallback/Boost) ---
    escaped_query = re.escape(query)
    # Regex to search anywhere within the title or caption (useful for long titles)
    phrase_regex = f".*{escaped_query}.*"
    phrase_condition = {
        "$or": [
            {"title": {"$regex": phrase_regex, "$options": "i"}},
            {"caption": {"$regex": phrase_regex, "$options": "i"}}
        ]
    }

    # Combine All-Word conditions (Logic 1) with Phrase condition (Logic 2)
    if all_word_conditions:
        # Prioritize results that match ALL words, OR results that match the exact phrase
        search_query = {
            "$or": [
                {"$and": all_word_conditions}, # All words present (word order independent)
                phrase_condition             # Exact phrase match (useful for names/titles)
            ]
        }
    else:
        # If the query was too short or contained only stop words, use only phrase match
        search_query = phrase_condition
        
    cursor = db.files_col.find(search_query).limit(10)
    files = await cursor.to_list(length=10)
    
    print(f"DEBUG: Found {len(files)} files for query '{query}'")
    
    return files

# Function to extract file details
def get_file_info(message: Message) -> tuple[str, str, Union[Document, Video, Audio, None]]:
    """Finds file_id, file_name, and file_object from a message."""
    if message.document and message.document.file_name:
        return message.document.file_id, message.document.file_name, message.document
    if message.video:
        file_name = message.caption.strip() if message.caption else f"Video_{message.id}"
        return message.video.file_id, file_name, message.video
    if message.audio:
        file_name = message.audio.file_name or message.audio.title or f"Audio_{message.id}"
        return message.audio.file_id, file_name, message.audio
    return None, None, None

# --- START COMMAND ---
@app.on_message(filters.command("start") & filters.private)
async def start_command(client, message: Message):
    """Handles the /start command in a private chat with custom text."""
    global IS_INDEXING_RUNNING
    
    if IS_INDEXING_RUNNING:
        await message.reply_text("Indexing is currently running. Please wait until it is complete.")
        return
        
    # User's customized start message
    await message.reply_text(
        "**𝚒'𝚖 𝚊𝚗 𝚊𝚍𝚟𝚊𝚗𝚌𝚎𝚍 𝚖𝚘𝚟𝚒𝚎𝚜 & 𝚜𝚎𝚛𝚒𝚎𝚜 𝚜𝚎𝚊𝚛𝚌𝚑 𝚋𝚘𝚝 & 𝚖𝚘𝚛𝚎 𝚏𝚎𝚊𝚝𝚞𝚛𝚎𝚜.!❤️**\n"
        "°•➤@Mala_Television🍿  \n"
        "°•➤@Mala_Tv \n"
        "°•➤@MalaTvbot  ™️\n"
        "🙂🙂\n\n"
        "To search for files, please type the name in a group or channel where I am an admin. Click the button there, and I will send the file to you privately here.\n\n"
        "**Admin Commands:**\n"
        "• `/index` - To index all files in the channel.\n"
        "• `/dbcount` - To check the number of files in the database."
    )
    print(f"DEBUG: Received start command from ID {message.from_user.id}")

@app.on_message(filters.command("index") & filters.user(ADMINS))
async def index_command(client, message: Message):
    """
    Command to index all files from the file store channel using the user session.
    """
    global IS_INDEXING_RUNNING
    
    if IS_INDEXING_RUNNING:
        await message.reply_text("❌ WARNING: Indexing process is currently running. Wait for the current job to complete.")
        return

    if PRIVATE_FILE_STORE == -100:
        await message.reply_text("PRIVATE_FILE_STORE ID is not provided in ENV. Indexing is not possible.")
        return
    
    if not USER_SESSION_STRING:
         await message.reply_text("❌ Indexing Error: **USER_SESSION_STRING** is not provided in ENV. Please generate and provide a user session string.")
         return

    IS_INDEXING_RUNNING = True # Set flag to True
    
    msg = await message.reply_text("🔑 Starting full automatic file indexing using user session... This may take time. (Check logs)")
    
    total_files_indexed = 0
    total_messages_processed = 0
    
    # --- INITIALIZE USER CLIENT FOR INDEXING ---
    user_client = Client(
        "indexer_session",
        api_id=API_ID,
        api_hash=API_HASH,
        session_string=USER_SESSION_STRING, # Logs in as user account
    )

    try:
        await user_client.start() # Starts the user client

        # Iterate through all messages using Pyrogram's get_chat_history
        async for chat_msg in user_client.get_chat_history(chat_id=PRIVATE_FILE_STORE): 
            total_messages_processed += 1
            file_id, file_name, file_object = get_file_info(chat_msg)
            
            if file_id and file_name:
                caption = chat_msg.caption.html if chat_msg.caption else None 
                
                try:
                    # Save/update file details in MongoDB
                    await db.files_col.update_one( 
                        {"file_id": file_id},
                        {
                            "$set": {
                                "title": file_name,
                                "caption": caption,
                                "file_id": file_id,
                                "chat_id": PRIVATE_FILE_STORE,
                                "message_id": chat_msg.id,
                                "media_type": file_object.__class__.__name__.lower()
                            }
                        },
                        upsert=True
                    )
                    total_files_indexed += 1
                    
                    if total_files_indexed % 50 == 0:
                         # Update status after every 50 files
                         try:
                             await msg.edit_text(f"✅ Indexed files: {total_files_indexed} / {total_messages_processed}")
                             print(f"INDEX_DEBUG: Successfully indexed {file_name}") 
                         except MessageNotModified:
                             pass # Ignore if text is the same.

                except Exception as db_error:
                    print(f"INDEX_DEBUG: DB WRITE error for file {file_name}: {db_error}")
            else:
                if chat_msg.text:
                    print(f"INDEX_DEBUG: Skipping text message {chat_msg.id}")
                else:
                    print(f"INDEX_DEBUG: Skipping message {chat_msg.id} - Not a supported file type (Doc/Vid/Aud).")
            
        # Final report after indexing is complete
        await msg.edit_text(f"🎉 Indexing complete! Total {total_files_indexed} files added or updated. ({total_messages_processed} messages processed)")
        
    except Exception as general_error:
        # Catch major errors like lack of channel access
        await msg.edit_text(f"❌ Indexing Error: {general_error}. Please check if the user account has access to the channel and the ID is correct.")
        print(f"INDEX_DEBUG: Fatal indexing error: {general_error}")
        
    finally:
        await user_client.stop() # Stops the user client
        IS_INDEXING_RUNNING = False # Set flag to False

@app.on_message(filters.command("dbcount") & filters.user(ADMINS))
async def dbcount_command(client, message: Message):
    """Command to check the total number of files in the database."""
    try:
        count = await db.files_col.count_documents({})
        await message.reply_text(f"📊 **Database File Count:**\nTotal indexed files: **{count}**")
    except Exception as e:
        await message.reply_text(f"❌ Error fetching database count: {e}")

# Auto-filter and Copyright Handler (Global)
@app.on_message(filters.text & filters.incoming & ~filters.command(["start", "index", "dbcount"])) 
async def global_handler(client, message: Message):
    """Handles all incoming text messages: copyright deletion and auto-filter search."""
    query = message.text.strip()
    chat_id = message.chat.id
    chat_type = message.chat.type
    
    # Check if indexing is running
    global IS_INDEXING_RUNNING
    if IS_INDEXING_RUNNING:
        await message.reply_text("Indexing is currently running. Please try again when the process is complete.")
        return
    
    print(f"DEBUG: Message received from chat {chat_id}: '{query}'")
    
    # --- 1. COPYRIGHT MESSAGE DELETION LOGIC ---
    COPYRIGHT_KEYWORDS = ["copyright", "unauthorized", "DMCA", "piracy"] 
    
    is_copyright_message = any(keyword.lower() in query.lower() for keyword in COPYRIGHT_KEYWORDS)
    is_protected_chat = chat_id == PRIVATE_FILE_STORE or chat_id in ADMINS
    
    if is_copyright_message and is_protected_chat:
        try:
            await message.delete()
            # Log the deletion
            await client.send_message(LOG_CHANNEL, f"🚫 **Copyright Message Deleted!**\n\n**Chat ID:** `{chat_id}`\n**User:** {message.from_user.mention}\n**Message:** `{query}`")
            return
        except Exception as e:
            print(f"Error deleting copyright message in chat {chat_id}: {e}")
            return
    
    print("DEBUG: Copyright check passed. Proceeding to filter.")
            
    # --- 2. AUTO-FILTER SEARCH (ONLY IN GROUPS/CHANNELS) ---
    
    # Skip filtering in private chats (DM)
    if chat_type == ChatType.PRIVATE:
        await message.reply_text("👋 To search for files, please type the name in a **group or channel** where I am an admin. Click the button there, and I will send the file here (in this DM).")
        return
        
    # Skip messages from the file store channel
    if chat_id == PRIVATE_FILE_STORE:
        print("DEBUG: Message came from PRIVATE_FILE_STORE, skipping filter.")
        return
        
    # --- SEARCH IN GROUPS AND CHANNELS ---
    
    files = await get_file_details(query)
    
    if files:
        # Files found: Send inline buttons
        text = f"Here are the files related to **{query}**:\n\nClick the button to get the file. The file will be sent to your private chat."
        buttons = []
        for file in files:
            media_icon = {"document": "📄", "video": "🎬", "audio": "🎶"}.get(file.get('media_type', 'document'), '❓')
            # Strip extension for cleaner button text
            file_name = file.get("title", "File").rsplit('.', 1)[0].strip() 
            
            buttons.append([
                InlineKeyboardButton(
                    text=f"{media_icon} {file_name}",
                    # Keep callback data short using message_id of the file
                    callback_data=f"getmsg_{file.get('message_id')}" 
                )
            ])
        
        if len(files) == 10:
             buttons.append([InlineKeyboardButton("More Results", url="https://t.me/your_search_group")]) 

        sent_message = await message.reply_text(
            text=text,
            reply_markup=InlineKeyboardMarkup(buttons),
            disable_web_page_preview=True
        )
        
        print(f"DEBUG: Sent filter results for search '{query}'. Starting autodelete timer.")
        
        # --- AUTODELETE LOGIC (after 60 seconds) ---
        await asyncio.sleep(60)
        try:
            await sent_message.delete()
            print("DEBUG: Autodelete complete.")
        except Exception as e:
            print(f"Error during autodelete: {e}")
            
                
# --- CALLBACK QUERY HANDLER (INLINE BUTTON CLICK) ---

@app.on_callback_query(filters.regex("^getmsg_")) 
async def send_file_handler(client, callback):
    """Sends the file privately when the inline button is clicked."""
    
    user_id = callback.from_user.id
    
    # Extract message_id from callback data
    message_id_str = callback.data.split("_")[1]
    message_id = int(message_id_str)
    
    # Force subscribe check (includes retry logic)
    if FORCE_SUB_CHANNEL and not await is_subscribed(client, user_id):
        # If the user has not subscribed, send a check button to DM
        join_button = [
            [InlineKeyboardButton("Join Channel", url=f"https://t.me/{FORCE_SUB_CHANNEL.replace('@', '')}")],
            # Button to check subscription again immediately in DM
            [InlineKeyboardButton("✅ Joined, Send File", callback_data=f"checksub_{message_id}")] 
        ]
        
        await callback.answer("Please join the channel to get the file. Click the button in DM after joining.", show_alert=True)
        # Send a message in DM asking to subscribe
        try:
            await client.send_message(
                chat_id=user_id,
                text=f"You must join the channel {FORCE_SUB_CHANNEL} to access the file. Please join and click the button below.",
                reply_markup=InlineKeyboardMarkup(join_button)
            )
        except Exception:
             # Cannot send message if user hasn't started the bot
             await callback.answer("File sending failed. Please send the /start command to the bot to begin a private chat.", show_alert=True)
             return
        return

    # If subscribed, proceed to send the file
    
    # Find the file in the database using message_id
    file = await db.files_col.find_one({"message_id": message_id}) 
    
    if file:
        try:
            # Forward the file from the original store channel to the user's private chat
            await client.forward_messages(
                chat_id=user_id, # <-- User's private chat ID
                from_chat_id=file['chat_id'],
                message_ids=file['message_id']
            )
            # Send a confirmation message in the user's private chat
            await client.send_message(user_id, "✅ You received the requested file.")
            
            await callback.answer("The file has been sent to your private chat.", show_alert=True)
            
        except Exception as e:
            # If forwarding fails (e.g., user blocked the bot or hasn't started the bot)
            await callback.answer("An error occurred while sending the file. Please check if you have sent the /start command to the bot.", show_alert=True)
            print(f"Error forwarding file to user {user_id}: {e}")
            
    else:
        await callback.answer("This file has been removed from the database.", show_alert=True)
    
    # Delete the message in the group/channel
    try:
        await callback.message.delete()
    except Exception as e:
        print(f"Error deleting inline message: {e}")

# --- NEW CALLBACK HANDLER FOR FORCE SUB CHECK IN DM ---
@app.on_callback_query(filters.regex("^checksub_")) 
async def check_sub_handler(client, callback):
    """Handles the 'Check Subscription and Send File' button in the private chat."""
    
    user_id = callback.from_user.id
    
    # Extract message_id from callback data
    message_id_str = callback.data.split("_")[1]
    message_id = int(message_id_str)

    # Re-check subscription without retries, as the user manually clicked this
    if FORCE_SUB_CHANNEL and not await is_subscribed(client, user_id, max_retries=1): 
        # Still not subscribed
        await callback.answer("❌ You have not joined the channel yet. Please try again.", show_alert=True)
        return
    
    # Subscription SUCCESS: Now send the file (reusing send logic)
    
    # Find the file in the database using message_id
    file = await db.files_col.find_one({"message_id": message_id}) 
    
    if file:
        try:
            # Forward the file from the original store channel to the user's private chat
            await client.forward_messages(
                chat_id=user_id, 
                from_chat_id=file['chat_id'],
                message_ids=file['message_id']
            )
            # Edit the original "Join Channel" message to say success
            await callback.message.edit_text("✅ Subscription confirmed. The file has been successfully sent.")
            
            await callback.answer("File sent.", show_alert=False)
            
        except Exception as e:
            await callback.answer("An error occurred while sending the file. Please check if you have sent the /start command to the bot.", show_alert=True)
            print(f"Error forwarding file to user {user_id}: {e}")
    else:
        await callback.answer("This file has been removed from the database.", show_alert=True)


# --- RENDER WEBHOOK SETUP (FastAPI) ---

# --- STARTUP/SHUTDOWN LIFECYCLE ---
async def startup_initial_checks():
    """Checks to run on startup."""
    print("Performing initial startup checks...")
    try:
        files_count = await db.files_col.count_documents({})
        print(f"Database check complete. Found {files_count} files in the database.")
    except Exception as e:
        print(f"WARNING: Database check failed on startup: {e}")


@asynccontextmanager
async def lifespan(web_app: FastAPI):
    await startup_initial_checks()
    
    if WEBHOOK_URL_BASE:
        await app.start() 
        await app.set_webhook(url=f"{WEBHOOK_URL_BASE}{WEBHOOK_PATH}")
        print(f"Webhook successfully set: {WEBHOOK_URL_BASE}{WEBHOOK_PATH}")
    else:
        await app.start()
        print("Starting in polling mode (for local testing only).")
        
    yield
    await app.stop()
    print("Application stopped.")

# FastAPI instance
api_app = FastAPI(lifespan=lifespan)

# Webhook endpoint for Telegram updates
@api_app.post(WEBHOOK_PATH)
async def process_update(request: Request):
    """Receives and processes Telegram updates."""
    try:
        req = await request.json()
        await app.process_update(req)
        return Response(status_code=HTTPStatus.OK)
    except Exception as e:
        print(f"Error processing update: {e}")
        return Response(status_code=HTTPStatus.INTERNAL_SERVER_ERROR)

# Render health check endpoint
@api_app.get("/")
async def health_check():
    """Render health check endpoint."""
    return {"status": "ok"}

# --- MAIN ENTRY POINT ---

if __name__ == "__main__":
    if WEBHOOK_URL_BASE:
        # Use uvicorn to serve the FastAPI app (for Render deployment)
        uvicorn.run("main:api_app", host="0.0.0.0", port=PORT, log_level="info")
    else:
        # Use app.run() for local polling mode testing
        print("Starting Pyrogram in polling mode...")
        asyncio.run(startup_initial_checks())
        app.run()
