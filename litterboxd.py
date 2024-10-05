import feedparser
import json
import os
import pytz
from telegram import Update, InlineQueryResultArticle, InputTextMessageContent
from telegram.ext import ApplicationBuilder, CommandHandler, InlineQueryHandler, ContextTypes
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from uuid import uuid4

# Cache for last movie logged for each user (persisted to a file)
last_logged_movies = {}

# Store subscribed users
subscribed_users = {}

# Load users and last logged movies from a JSON file
def load_data():
    global subscribed_users, last_logged_movies
    if os.path.exists('users.json'):
        with open('users.json', 'r') as file:
            subscribed_users = json.load(file)
    if os.path.exists('last_logged_movies.json'):
        with open('last_logged_movies.json', 'r') as file:
            last_logged_movies = json.load(file)

# Save users and last logged movies to a JSON file
def save_data():
    with open('users.json', 'w') as file:
        json.dump(subscribed_users, file)
    with open('last_logged_movies.json', 'w') as file:
        json.dump(last_logged_movies, file)

# Function to fetch the latest logged movies (last `count` movies) from the RSS feed
def get_latest_movies(rss_url, count=5):
    feed = feedparser.parse(rss_url)
    if feed.entries:
        movies = [(entry.title, entry.link) for entry in feed.entries[:count]]
        return movies
    return []

# Function to construct the Letterboxd RSS feed URL from username
def construct_rss_url(username):
    return f"https://letterboxd.com/{username}/rss/"

# Command handler for /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Send me your Letterboxd username using the /rss command!")

# Command handler for fetching movies using username
async def fetch_movie(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if context.args:
        username = context.args[0]  # Get the username from command arguments
        rss_url = construct_rss_url(username)  # Construct the RSS URL
        movies = get_latest_movies(rss_url, count=5)  # Fetch the last 5 movies
        if movies:
            movie_info = "\n\n".join([f"{title}\nWatch it here: {link}" for title, link in movies])
            await update.message.reply_text(movie_info)
        else:
            await update.message.reply_text("No recent movies logged or invalid username.")
    else:
        await update.message.reply_text("Please provide a Letterboxd username.")

# Subscribe a user to notifications
async def subscribe(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if context.args:
        username = context.args[0]
        chat_id = update.message.chat_id
        subscribed_users[chat_id] = username
        save_data()  # Save subscribed users and movie logs
        await update.message.reply_text(f"Subscribed to updates for {username}!")
    else:
        await update.message.reply_text("Please provide your Letterboxd username.")

# Unsubscribe a user from notifications
async def unsubscribe(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.message.chat_id
    if chat_id in subscribed_users:
        del subscribed_users[chat_id]
        save_data()  # Save data
        await update.message.reply_text("You have been unsubscribed from notifications.")
    else:
        await update.message.reply_text("You are not subscribed.")

# List user subscriptions
async def list_subscriptions(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.message.chat_id
    if chat_id in subscribed_users:
        username = subscribed_users[chat_id]
        await update.message.reply_text(f"You are subscribed to updates for: {username}")
    else:
        await update.message.reply_text("You are not subscribed to any usernames.")

# Notify users of new movies, but avoid duplicates
async def check_for_new_movies(context: ContextTypes.DEFAULT_TYPE) -> None:
    for chat_id, username in subscribed_users.items():
        rss_url = construct_rss_url(username)
        movies = get_latest_movies(rss_url, count=1)  # Fetch only the latest movie
        if movies:
            title, link = movies[0]
            # Only notify if the movie is new (i.e., not shown before)
            if last_logged_movies.get(username) != title:
                await context.bot.send_message(chat_id=chat_id, text=f"New movie logged by {username}: {title}\nWatch it here: {link}")
                last_logged_movies[username] = title
                save_data()  # Save the last logged movies to prevent repeat notifications

# Inline query handler to search for movies
async def inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.inline_query.query
    if query == "":
        return

    rss_url = construct_rss_url(query)
    movies = get_latest_movies(rss_url, count=1)  # Fetch only the latest movie
    if movies:
        title, link = movies[0]
        results = [
            InlineQueryResultArticle(
                id=str(uuid4()),
                title=title,
                input_message_content=InputTextMessageContent(f"{query} just watched: {title}\nWatch it here: {link}")
            )
        ]
        await update.inline_query.answer(results)

# Main function to start the bot
def main():
    # Load user subscriptions and last logged movies from disk
    load_data()

    # Bot Token (You should use environment variables for security)
    TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')

    # Create the application and add the handlers
    application = ApplicationBuilder().token(TOKEN).build()

    # Add command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("rss", fetch_movie))
    application.add_handler(CommandHandler("subscribe", subscribe))
    application.add_handler(CommandHandler("unsubscribe", unsubscribe))
    application.add_handler(CommandHandler("list", list_subscriptions))

    # Add inline query handler
    application.add_handler(InlineQueryHandler(inline_query))

    # Set up scheduler to check every 5 seconds
    scheduler = AsyncIOScheduler(timezone=pytz.UTC)  # You can change the timezone as needed
    scheduler.add_job(check_for_new_movies, 'interval', seconds=5, args=[application])
    scheduler.start()

    # Start polling
    application.run_polling()

if __name__ == '__main__':
    main()
