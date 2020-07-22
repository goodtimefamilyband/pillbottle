from .classes import Action
import discord

async def getAction(entry, bot, eserverid):
    server = discord.utils.find(lambda s: s.id == eserverid, bot.servers)
    if server is None:
        return None
        
    echannel = discord.utils.find(lambda c: c.id == entry.echannel, server.channels)
    if echannel is None:
        return None
    
    rchannel = await bot.fetch_user(entry.channelid)
    
    return Action(bot, rchannel, entry.message, everyone=echannel, requests=entry.requestcount, timeout=entry.timeout, response=entry.response)
