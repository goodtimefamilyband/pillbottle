# pillbottle.py

import asyncio
import time
import sched
import discord
from discord.ext import commands
import re
from sqlalchemy import func

#from pillbottle import getAction
from pillbottle.classes import RegexChecker, DateChecker, ReminderConvo, SetupConvo
from pillbottle.schema import Session, CronEntry, Channel, User, Response, db
from sqlalchemy.orm import aliased

import sys

if len(sys.argv) < 2:
    print("Usage: {} bot-token [bot-master-id]\n".format(sys.argv[0]))
    sys.exit()

token = sys.argv[1]
    
botmaster = "0"
if len(sys.argv) > 2:
    botmaster = sys.argv[2]

#db = Session()

cronorder = ["hourly", "daily", "monthly", "yearly", "weekly"]
qorder = ["hourly", "daily", "weekly", "monthly", "yearly"]
qre = re.compile("|".join(qorder))

entries = {}
convos = {}

qdict = { 
"hourly" : "What minute?",
"daily" : "What hour?",
"weekly" : "What day(s)?",
"monthly" : "What day?",
"yearly" : "What month?"
}

bot = commands.Bot(command_prefix="p.")

def checknumber(msg):
    pass        
    
def getDbEntry(entryid):
    echannels = aliased(Channel)
    dbentry = db.query(CronEntry, echannels.serverid).join(echannels, CronEntry.echannel == echannels.id).filter(CronEntry.id==entryid).first()
    
    return dbentry
    
def checkPermissions(entryid, userid):
    global botmaster
    
    echannels = aliased(Channel)

    query = db.query(CronEntry, echannels.serverid)\
    .join(echannels, CronEntry.echannel == echannels.id)\
    .filter(CronEntry.id==entryid)
    
    print(userid, type(userid), botmaster, type(botmaster), userid != botmaster)
    if userid != botmaster:
        query = query.filter(CronEntry.userid==userid)
    
    return query.first()
    
async def processEntryId(entryid, ctx):
    try:
        return int(entryid)
    except ValueError:
        pass
        
    if not entryid in entries:
        await ctx.bot.send_message(ctx.message.channel, "Nothing scheduled with that ID ({})".format(entryid))
        return None
    

@bot.listen()
async def on_ready():
    global entries

    print("Logged in")
    uchannels = aliased(Channel)
    echannels = aliased(Channel)
    for (entry, userid, channelid, serverid) in db.query(CronEntry, uchannels.id, echannels.id, echannels.serverid)\
    .join(uchannels, CronEntry.channelid == uchannels.id)\
    .join(echannels, CronEntry.echannel == echannels.id):
        
        if not entry.id in entries:
            entries[entry.id] = entry
            entry.bot = bot
            
            convos[entry.id] = ReminderConvo(entry, db)
            bot.loop.create_task(convos[entry.id].run())
        
    print(entries)
    
@bot.command(pass_context=True, no_pm=False)
async def remind(ctx, *msg):
    '''Create a new reminder
    
    Sends the reminder to the channel on which the command was sent. Will ask you a series of questions about the reminder time, where to send additional reminders, etc.
    
    msg -- The content of the reminder. Sent to you on the channel you specify
    '''
    
    global entries
    
    message = " ".join(msg)
    user = ctx.message.author
    uchannel = ctx.message.channel
    
    print(user, user.id, uchannel, uchannel.id, ctx.bot.get_channel(uchannel.id))
    print(ctx.bot.private_channels)
    
    if len(ctx.message.mentions) > 0:
        user = ctx.message.mentions[0]
    
    convo = SetupConvo(ctx)
    
    await convo.run()
    
    centry = convo.getNewEntry(message, db)     
    centry.bot = ctx.bot
    
    rconvo = ReminderConvo(centry, db)
    ctx.bot.loop.create_task(rconvo.run())
    
    entries[centry.id] = centry
    convos[centry.id] = rconvo
    
    await ctx.bot.send_message(ctx.message.channel, "Reminder set! ({})".format(centry.id))
    
    print(convo.dc.datetime)
    print(convo.server)
    print(convo.channel)
        
@bot.command(pass_context=True, no_pm=False)
async def schedule(ctx):
    '''List all active reminders
    
    When sent in a public channel, lists all reminders active on that server.
    When sent in a private channel, lists all reminders visible to the user who issued the command.
    '''
    uchannels = aliased(User)
    echannels = aliased(Channel)
    entrylist = []
    
    query = db.query(CronEntry, uchannels.id, echannels.id, echannels.serverid)\
    .join(uchannels, CronEntry.userid == uchannels.id)\
    .join(echannels, CronEntry.echannel == echannels.id)
    
    if ctx.message.server is None:
        dbentries = query.filter(uchannels.id==ctx.message.author.id)
    else:
        dbentries = query.filter(echannels.serverid==ctx.message.server.id)
    
    for (entry, userid, channelid, serverid) in dbentries:
        if entry is not None and entry.id in entries:
            centry = entries[entry.id]
            crontab = entry.cron.split(" ")
            t = "{}:{}".format(crontab[1], crontab[0].zfill(2))
            
            await centry.wait_for_discord()
            
            entrylist.append("{}: {} {} @{} {}#{}".format(entry.id, t, entry.message, centry.user.name, centry.everyone.server.name, centry.everyone.name))
            
    msg = "Nothing scheduled"
    if len(entrylist) != 0:
        msg = "\n".join(entrylist)
            
    await ctx.bot.send_message(ctx.message.channel, "```Times are in UTC 24-hour format.\n{}```".format(msg))

@bot.command(pass_context=True, no_pm=False)    
async def setuser(ctx, entryid, *user):
    '''Sets the recipient of a reminder.
    
    You must include at least one user. Additionally, you may mention a channel to have the initial reminders delivered to that channel.
    Only the recipient of a reminder may make changes to or delete it. If you set the recipient to someone other than yourself, you will no longer be able to change the reminder.
    
    entryid -- The ID of the reminder to change. View reminder IDs with p.schedule
    user -- A list of mentions containing at least one user and optionally a channel
    '''
    
    if len(ctx.message.mentions) != 1:
        await ctx.bot.send_message(ctx.message.channel, "Not sure whom to remind...")
        return
    
    #dbentry = db.query(CronEntry, echannels.serverid).join(echannels, CronEntry.channelid == echannels.id).filter(CronEntry.id==entryid).first()
    dbentry = checkPermissions(entryid, ctx.message.author.id)
    if dbentry is None:
        await ctx.bot.send_message(ctx.message.channel, "Nothing scheduled with that ID")
        return
    
    entryid = int(entryid)
    centry = entries[entryid]
    centry.user = ctx.message.mentions[0]
    
    if len(ctx.message.channel_mentions) == 1:
        centry.channel = ctx.message.channel_mentions[0]
    else:
        centry.channel = await ctx.message.mentions[0].create_dm()
    
    db.commit()
    await convos[entryid].cancel()
    convos[entryid] = ReminderConvo(centry, db)
    bot.loop.create_task(convos[entryid].run())
    
    await ctx.bot.send_message(ctx.message.channel, "User set to {}".format(ctx.message.mentions[0].mention))
    
@bot.command(pass_context=True, no_pm=False)
async def setmessage(ctx, entryid, *content):
    '''Sets the content of a reminder
    
    entryid -- The ID of the reminder to change. View reminder IDs with p.schedule
    content -- The new content of the reminder.
    '''
    
    entryid = await processEntryId(entryid, ctx)
    if entryid is None:
        return
    
    dbentry = checkPermissions(entryid, ctx.message.author.id)
    if dbentry is None:
        await ctx.bot.send_message(ctx.message.channel, "You can't change that reminder")
        return
    
    entry = entries[entryid]
    entry.message = " ".join(content)
    
    db.commit()
    
    await ctx.bot.send_message(ctx.message.channel, "Message set")
    
@bot.command(pass_context=True, no_pm=False)
async def settime(ctx, entryid, *t):
    '''Sets the time at which a reminder is issued
    
    entryid -- The ID of the reminder to change. View reminder IDs with p.schedule
    t -- A clock time.  Current default time zone is EST.
    
    Other timezones are not currently supported because coding for multiple timezones is annoying.  Support for other timezones may be added in a future release.
    '''
    
    entryid = await processEntryId(entryid, ctx)
    if entryid is None:
        return
    
    dbentry = checkPermissions(entryid, ctx.message.author.id)
    if dbentry is None:
        await ctx.bot.send_message(ctx.message.channel, "You can't change that reminder")
        return
    
    dc = DateChecker()
    if not dc.checktime(" ".join(t)):
        await ctx.bot.send_message("I don't understand the time {}".format(timestr))
        return
    
    entry = entries[entryid]
    #entry.crontab.stop()
    
    crontab = dc.get_crontab()
    entry.cron = crontab
    entry.next_run = None
    db.commit()
    
    await convos[entryid].cancel()
    convos[entryid] = ReminderConvo(entry, db)
    bot.loop.create_task(convos[entryid].run())
    
    await ctx.bot.send_message(ctx.message.channel, "Time updated")
    
@bot.command(pass_context=True, no_pm=False)
async def settimeout(ctx, entryid, timeout):
    '''Sets how long the bot waits before reminding you again, or reminding others
    
    entryid -- The ID of the reminder to change. View reminder IDs with p.schedule
    timeout -- The length of time (in seconds) before the bot sends another reminder. After three reminders, the bot sends the reminder to a public channel.
    
    The default is currently 5 seconds, so you may want to set this higher.
    '''
    
    entryid = await processEntryId(entryid, ctx)
    if entryid is None:
        return
        
    dbentry = checkPermissions(entryid, ctx.message.author.id)
    if dbentry is None:
        await ctx.bot.send_message(ctx.message.channel, "You can't change that reminder")
        return
        
    if not timeout.isdigit() and not int(timeout) > 0:
        await ctx.bot.send_message(ctx.message.channel, "Timeout should be a number > 0")
        return
        
    entry = entries[entryid]
    entry.timeout = int(timeout)
    db.commit()
    
    await ctx.bot.send_message(ctx.message.channel, "Timeout set")
        
@bot.command(pass_context=True, no_pm=True)
async def setrole(ctx, entryid, *role):
    '''Sets a role for the bot to mention when sending public reminders
    
    entryid -- The ID of the reminder to change. View reminder IDs with p.schedule
    role -- A role mention for the bot to use when issuing public reminders
    '''
    
    entryid = await processEntryId(entryid, ctx)
    if entryid is None:
        return
        
    dbentry = checkPermissions(entryid, ctx.message.author.id)
    if dbentry is None:
        await ctx.bot.send_message(ctx.message.channel, "No entry with that id")
        return
        
    if len(ctx.message.role_mentions) == 0:
        await ctx.bot.send_message(ctx.message.channel, "Please mention a role to receive extra reminders")
        return
        
    entries[entryid].role = ctx.message.role_mentions[0]
    db.commit()
    
    await ctx.bot.send_message(ctx.message.channel, "Role set")

@bot.command(pass_context=True, no_pm=False)
async def setpassphrase(ctx, entryid, *passphrase):
    '''Sets a pass phrase for the recipient to use when dismissing a reminder
    
    The recipient must respond with the given passphrase exactly. All other messages in response to a reminder will be ignored, and the bot will issue additional reminders until it receives a message consists of the exact passphrase set by this command.
    
    entryid -- The ID of the reminder to change. View reminder IDs with p.schedule
    passphrase -- The content a reminder response must contain in order to dismiss it.
    '''

    entryid = await processEntryId(entryid, ctx)
    if entryid is None:
        return
        
    dbentry = checkPermissions(entryid, ctx.message.author.id)
    if dbentry is None:
        await ctx.bot.send_message(ctx.message.channel, "No entry with that id")
        return
    
    if len(passphrase) == 0:
        await ctx.bot.send_message(ctx.message.channel, "Passphrase cannot be empty")
        
    entries[entryid].passphrase = " ".join(passphrase)
    db.commit()
    
    await ctx.bot.send_message(ctx.message.channel, "Passphrase set")
    
@bot.command(pass_context=True, no_pm=False)
async def remove(ctx, entryid):
    '''Removes a reminder
    
    entryid -- The ID of the reminder to remove. View reminder IDs with p.schedule
    '''
    
    entryid = await processEntryId(entryid, ctx)
    if entryid is None:
        return
        
    dbentry = checkPermissions(entryid, ctx.message.author.id)
    if dbentry is None:
        await ctx.bot.send_message(ctx.message.channel, "You can't remove that item")
        return
            
    entry = entries[entryid]
    db.delete(entry)
    db.commit()
    
    await convos[entryid].cancel()
    
    del entries[entryid]
    del convos[entryid]
    
    await ctx.bot.send_message(ctx.message.channel, "Reminder removed")
    
@bot.command(pass_context=True, no_pm=False)
async def addresponse(ctx, entryid, *resp):
    '''Adds a possible response for the bot to give
    
    When the user successfully dismisses a reminder, the bot responds with a randomly selected response added via this command.
    
    entryid -- The ID of the reminder to change. View reminder IDs with p.schedule
    resp -- The content of the bot's response. Try words of affirmation
    '''
    
    entryid = await processEntryId(entryid, ctx)
    if entryid is None:
        return
        
    dbentry = checkPermissions(entryid, ctx.message.author.id)
    if dbentry is None:
        await ctx.bot.send_message(ctx.message.channel, "You can't change that item")
        return
        
    (rcount,) = db.query(func.count(Response.id)).filter_by(entryid=entryid).first()
    db.add(Response(id=rcount+1, entryid=entryid, text=" ".join(resp)))
    db.commit()
    
    await ctx.bot.send_message(ctx.message.channel, "Response added")
    
@bot.command(pass_context=True, no_pm=False)
async def responses(ctx, entryid):
    '''List the responses for a given reminder, along with their IDs
    
    When the user successfully dismisses a reminder, the bot responds with a response randomly selected from this list.
    
    entryid -- The ID of the reminder to list responses for. View reminder IDs with p.schedule
    '''

    entryid = await processEntryId(entryid, ctx)
    if entryid is None:
        return
        
    dbentry = checkPermissions(entryid, ctx.message.author.id)
    if dbentry is None:
        await ctx.bot.send_message(ctx.message.channel, "You can't change that item")
        return
        
    responses = db.query(Response).filter_by(entryid=entryid).all()
    rlist = "\n".join(["{} {}".format(r.id, r.text) for r in responses]) if len(responses) > 0 else "No responses"
    
    msg = "```{}```".format(rlist)
    await ctx.bot.send_message(ctx.message.channel, msg)
    
@bot.command(pass_context=True, no_pm=False)
async def removeresponse(ctx, entryid, responseid):
    '''Remove a response
    
    entryid -- The ID of the reminder to change. View reminder IDs with p.schedule
    responseid -- The ID of the response to remove.  View response IDs with p.responses
    '''

    entryid = await processEntryId(entryid, ctx)
    if entryid is None:
        return
        
    dbentry = checkPermissions(entryid, ctx.message.author.id)
    if dbentry is None:
        await ctx.bot.send_message(ctx.message.channel, "You can't change that item")
        return
    
    response = db.query(Response).filter_by(entryid=entryid, id=responseid).first()
    if response is not None:
        db.delete(response)
        db.commit()
        
        await ctx.bot.send_message(ctx.message.channel, "Response removed")
    
print("Running pillbottle...")
bot.run(token)
