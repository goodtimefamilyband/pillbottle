# pillbottle.py

import asyncio
import time
import sched
import discord
from discord.ext import commands
import re

#from pillbottle import getAction
from pillbottle.classes import RegexChecker, DateChecker, ReminderConvo, SetupConvo
from pillbottle.schema import Session, CronEntry, Channel, User, db
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
        
        entries[entry.id] = entry
        entry.bot = bot
        #entry.schedule()
        
        '''
        channel = await entry.channel
        channel = bot.get_channel(channel.id)
        
        everyone = await entry.everyone
        '''
        convos[entry.id] = ReminderConvo(entry, db)
        bot.loop.create_task(convos[entry.id].run())
        
    print(entries)
    
@bot.command(pass_context=True, no_pm=False)
async def remind(ctx, *args, **kwargs):
    global entries
    
    message = " ".join(args)
    user = ctx.message.author
    uchannel = ctx.message.channel
    
    print(user, user.id, uchannel, uchannel.id, ctx.bot.get_channel(uchannel.id))
    print(ctx.bot.private_channels)
    
    if len(ctx.message.mentions) > 0:
        user = ctx.message.mentions[0]
    
    convo = SetupConvo(ctx)
    
    await convo.run()
    
    '''
    entry = "{} {} * * *".format(convo.dc.datetime.minute, convo.dc.datetime.hour)
    
    uchan = db.query(Channel).filter_by(id=user.id).first()
    if uchan is None:
        uchan = Channel(id=ctx.message.author.id, serverid=None)
        db.add(uchan)
        
    echan = db.query(Channel).filter_by(id=convo.channel.id).first()
    if echan is None:
        echan = Channel(id=convo.channel.id, serverid=convo.channel.server.id)
        db.add(echan)
        
    centry = CronEntry(channelid=uchan.id, 
    message=message, 
    timeout=900, 
    requestcount=3, 
    echannel=echan.id, 
    response="Thank you!",
    cron=entry)
    '''
    
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
    
    '''
    await ctx.bot.send_message(ctx.message.channel, "ok")
    
    
    dc = DateChecker()
    await ctx.bot.send_message(ctx.message.channel, "Reminders are daily.  What time would you like to be reminded?")
    reply = await ctx.bot.wait_for_message(author=ctx.message.author, channel=ctx.message.channel, check=dc)
    
    if reply is None:
        return
    
    entry = "{} {} * * *".format(dc.datetime.minute, dc.datetime.hour)
    
    dest_server = None
    member = None
    
    while dest_server is None:
        await ctx.bot.send_message(ctx.message.channel, "Which server do you want to notify you for extra reminders?")
    
        reply = await ctx.bot.wait_for_message(author=ctx.message.author, channel=ctx.message.channel)
        dest_server = discord.utils.find(lambda s : s.name == reply.content, ctx.bot.servers)
        
        if dest_server is None:
            await ctx.bot.send_message(ctx.message.channel, "I don't have access to {}.".format(reply.content))
            continue
                
        botmember = discord.utils.find(lambda m: m.id == ctx.bot.user.id, dest_server.members)
        member = discord.utils.find(lambda m : m.id == ctx.message.author.id, dest_server.members)
        
        print(type(botmember), type(member))
        
        if member is None:
            dest_server = None
            await ctx.bot.send_message(ctx.message.channel, "You're not a member of {}.".format(reply.content))
            continue
                
        possible_channels = [channel for channel in dest_server.channels if channel.permissions_for(member).read_messages and channel.permissions_for(botmember).send_messages and channel.type == discord.ChannelType.text]
        
        if len(possible_channels) == 0:
            await ctx.bot.send_message(ctx.message.channel, "You can't read any messages of channels that I can send to in {}...".format(reply.content))
            dest_server = None
        else:
            clist = "\n".join(["{}. {}".format(i, possible_channels[i].name) for i in range(len(possible_channels))])
            
            await ctx.bot.send_message(ctx.message.channel, "Select a channel:\n" + clist)
        
            reply = await ctx.bot.wait_for_message(channel=ctx.message.channel, 
            author=ctx.message.author, 
            check=lambda m : m.content.isdigit() and int(m.content) < len(possible_channels))
            
            dest_channel = possible_channels[int(reply.content)]
            
            #a = Action(ctx.bot, ctx.message.author, message, everyone=dest_channel)
            #cron = aiocron.crontab(entry, func=a, loop=ctx.bot.loop)
            #centry = a.getDbObj(db)
            
            uchan = db.query(Channel).filter_by(id=ctx.message.author.id).first()
            if uchan is None:
                uchan = Channel(id=ctx.message.author.id, serverid=None)
                db.add(uchan)
                
            echan = db.query(Channel).filter_by(id=dest_channel.id).first()
            if echan is None:
                echan = Channel(id=dest_channel.id, serverid=dest_channel.server.id)
                db.add(echan)
                
            centry = CronEntry(channelid=uchan.id, 
            message=message, 
            timeout=900, 
            requestcount=3, 
            echannel=echan.id, 
            response="Thank you!",
            cron=entry)
            
            db.add(centry)
            db.commit()
            
            centry.bot = ctx.bot
            centry.schedule()
            entries[centry.id] = centry
            
            await ctx.bot.send_message(ctx.message.channel, "Reminder set! ({})".format(centry.id))    
    '''

'''
@bot.command(pass_context=True, no_pm=False)
async def set(ctx, *args, **kwargs):
    message = " ".join(args)
    check = MessageChecker(qre)
    
    await ctx.bot.send_message(ctx.message.channel, "How often would you like to be reminded?")
    reply = await ctx.bot.wait_for_message(author=ctx.message.author, channel=ctx.message.channel, check=check)
    
    if reply is not None:
        found = False
        s,e = check.match.span()
        freq = reply.content[s:e]
        tparams = {}
        
        for q in qorder[::-1]:
            
            if freq == q:
                found = True
            
            #TODO: validate entries
            if found:
                await ctx.bot.send_message(ctx.message.channel, qdict[q])
                reply = await ctx.bot.wait_for_message(author=ctx.message.author, channel=ctx.message.channel)
                if reply is not None:
                    tparams[q] = reply.content
        
        entry = " ".join([tparams[f] if f in tparams else "*" for f in cronorder])
        
        dest_server = None
        member = None
        
        while dest_server is None:
            await ctx.bot.send_message(ctx.message.channel, "Which server do you want to notify you for extra reminders?")
        
            reply = await ctx.bot.wait_for_message(author=ctx.message.author, channel=ctx.message.channel)
            dest_server = discord.utils.find(lambda s : s.name == reply.content, ctx.bot.servers)
            
            if dest_server is None:
                await ctx.bot.send_message(ctx.message.channel, "I don't have access to {}.".format(reply.content))
            else:
                botmember = discord.utils.find(lambda m: m.id == ctx.bot.user.id, dest_server.members)
                member = discord.utils.find(lambda m : m.id == ctx.message.author.id, dest_server.members)
                if member is None:
                    dest_server = None
                    await ctx.bot.send_message(ctx.message.channel, "You're not a member of {}.".format(reply.content))
                else:
                    possible_channels = [channel for channel in dest_server.channels if channel.permissions_for(ctx.message.author).read_messages and channel.permissions_for(botmember).send_messages]
                    
                    if len(possible_channels) == 0:
                        await ctx.bot.send_message(ctx.message.channel, "You can't read any messages of channels that I can send to in {}...".format(reply.content))
                        dest_server = None
                    else:
                        clist = "\n".join(["{}. {}".format(i, possible_channels[i].name) for i in range(len(possible_channels))])
                        
                        await ctx.bot.send_message(ctx.message.channel, "Select a channel:\n" + clist)
                    
                        reply = await ctx.bot.wait_for_message(channel=ctx.message.channel, 
                        author=ctx.message.author, 
                        check=lambda m : m.content.isdigit() and int(m.content) < len(possible_channels))
                        
                        dest_channel = possible_channels[int(reply.content)]
                        
                        a = Action(ctx.bot, ctx.message.author, message, everyone=dest_channel)
                        cron = aiocron.crontab(entry, func=a, loop=ctx.bot.loop)
                        centry = a.getDbObj(db)
                        centry.cron = entry
                        db.add(centry)
                        db.commit()
                        
                        entries[centry.id] = {"action": a, "cron": cron}
                        
                        await ctx.bot.send_message(ctx.message.channel, "Reminder set! ({})".format(centry.id))
'''    
    
@bot.command(pass_context=True, no_pm=False)
async def schedule(ctx, *args, **kwargs):
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
async def setuser(ctx, entryid, *args, **kwargs):
    
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
        centry.channel = await bot.start_private_message(ctx.message.mentions[0])
    
    db.commit()
    await convos[entryid].cancel()
    convos[entryid] = ReminderConvo(centry, db)
    bot.loop.create_task(convos[entryid].run())
    
    await ctx.bot.send_message(ctx.message.channel, "User set to {}".format(ctx.message.mentions[0].mention))
    
@bot.command(pass_context=True, no_pm=False)
async def setresponse(ctx, entryid, *args, **kwargs):
    global entries
    
    entryid = await processEntryId(entryid, ctx)
    if entryid is None:
        return
        
    dbentry = checkPermissions(entryid, ctx.message.author.id)
    if dbentry is None:
        await ctx.bot.send_message(ctx.message.channel, "You can't change that reminder")
        return
    
    centry = entries[entryid]
    centry.response = " ".join(args)
    
    db.commit()
    
    await ctx.bot.send_message(ctx.message.channel, "Response set")
    
@bot.command(pass_context=True, no_pm=False)
async def setmessage(ctx, entryid, *args, **kwargs):
    
    entryid = await processEntryId(entryid, ctx)
    if entryid is None:
        return
    
    dbentry = checkPermissions(entryid, ctx.message.author.id)
    if dbentry is None:
        await ctx.bot.send_message(ctx.message.channel, "You can't change that reminder")
        return
    
    entry = entries[entryid]
    entry.message = " ".join(args)
    
    db.commit()
    
    await ctx.bot.send_message(ctx.message.channel, "Message set")
    
@bot.command(pass_context=True, no_pm=False)
async def settime(ctx, entryid, *args, **kwargs):
    
    entryid = await processEntryId(entryid, ctx)
    if entryid is None:
        return
    
    dbentry = checkPermissions(entryid, ctx.message.author.id)
    if dbentry is None:
        await ctx.bot.send_message(ctx.message.channel, "You can't change that reminder")
        return
    
    dc = DateChecker()
    if not dc.checktime(" ".join(args)):
        await ctx.bot.send_message("I don't understand the time {}".format(timestr))
        return
    
    entry = entries[entryid]
    #entry.crontab.stop()
    
    crontab = dc.get_crontab()
    entry.cron = crontab
    db.commit()
    
    await convos[entryid].cancel()
    convos[entryid] = ReminderConvo(entry, db)
    bot.loop.create_task(convos[entryid].run())
    
    await ctx.bot.send_message(ctx.message.channel, "Time updated")
    
@bot.command(pass_context=True, no_pm=False)
async def settimeout(ctx, entryid, timeout):
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
    
@bot.command(pass_context=True, no_pm=False)
async def notifyeveryone(ctx, entryid):
    
    entryid = await processEntryId(entryid, ctx)
    if entryid is None:
        return
        
    dbentry = checkPermissions(entryid, ctx.message.author.id)
    if dbentry is None:
        await ctx.bot.send_message(ctx.message.channel, "You can't change that reminder")
        return
        
    entry = entries[entryid]
    
   
@bot.command(pass_context=True, no_pm=False)
async def remove(ctx, entryid):
    
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
    
print("Running pillbottle...")
bot.run(token)
