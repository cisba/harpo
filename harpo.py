#!/usr/bin/python3
import sys 
import os
import yaml
import logging
import time
import datetime
import re
import subprocess 
import fnmatch
from telegram.ext import Updater, CommandHandler
from telegram.ext import MessageHandler, Filters
from telegram import Bot
from telegram.ext import BaseFilter

# Utils functions
def confload(bot=None,update=None):
    # read file
    global cfg
    with open(sys.argv[1], 'r') as yml_file: 
        cfg = yaml.load(yml_file)
    # create path for youtube download and extract tempdir
    if not os.path.exists(cfg['ydax_tmpdir']):
        os.makedirs(cfg['ydax_tmpdir'])
    # get numeric loglevel
    numeric_level = getattr(logging, cfg['loglevel'].upper(), None)
    if not isinstance(numeric_level, int):
        raise ValueError('Invalid log level: %s' % loglevel)
    # config logging
    logging.basicConfig(level=numeric_level,
                filename=cfg['logfile'], 
                format='%(asctime)s %(name)-12s %(levelname)-8s %(message)s',
                datefmt='%Y-%m-%d %H:%M')
    logging.info("config loaded")

def check_auth(bot, update):
    if update.message.from_user.id not in cfg['acl']:
        text="You are not authorized to use this bot."
        bot.sendMessage(chat_id=update.message.chat_id, text=text) 
        return False
    else:
        return True

def filter_any(msg):
    logging.debug('Received message_id: '+str(msg.message_id))
    if msg.text:
        logging.debug('text: '+msg.text)
    elif msg.document:
        logging.debug('document: '+msg.document.file_name)
    return False

def tail(f, n):
    out = subprocess.check_output(["tail", "-n", str(n), f])
    return out.decode("utf-8")

# Telegram commands

def start(bot, update):
    if not check_auth(bot, update): return
    text="You are authorized."
    bot.sendMessage(chat_id=update.message.chat_id, text=text) 

def sincro(bot, update):
    if not check_auth(bot, update): return
    stamp = time.localtime(os.path.getmtime(cfg['sincro_log']))
    report = time.strftime("%a %d %b %Y at %H:%M:%S\n", stamp)
    with open(cfg['sincro_log'],'r') as f:
        for line in f:
            if "transferred" in line or "JOB:" in line:
                report = report + line
    bot.sendMessage(chat_id=update.message.chat_id, text=report)

def btc(bot,update,args):
    if not check_auth(bot, update): return
    if len(args) == 0:
        text = btc_stat([ 5 ])
    elif args[0] == 'help':
        text = str(cfg['btc']['cmds'])
    elif len(args) > 0 and args[0] in cfg['btc']['cmds']:
        text = btc_cmd(args)
    else:
        text = str(args[0]) + ' is not a valid argument'
    bot.sendMessage(chat_id=update.message.chat_id, text=text)
    return 

def btc_cmd(args):
    logging.info("executing: " + " ".join(cfg['btc']['exec'] + args))
    try:
        outs = subprocess.check_output(cfg['btc']['exec'] + args)
    except subprocess.CalledProcessError as cmd_error:
        text = "bitcoin-cli error: " + str(cmd_error.returncode) \
                            + " " + str(cmd_error.output)
        logging.error(text)
    else:
        text = outs.decode("utf-8") 
    return text

def btc_stat(args):
    # check arguments
    if len(args) == 0:
        n = 10
    elif len(args) == 1 and isinstance(args[0], int):
        n = args[0]
    else:
        return args[0] + ' is not a number'
    return tail(cfg['btc_stat'], n)

def ydax(bot, update):
    if not check_auth(bot, update): return
    url = update.message.text
    logging.debug("executing youtube-dl -x " + url)
    cmd = [ 'youtube-dl', '--restrict-filenames' ]
    try:
        out = subprocess.check_output(cmd + ['--get-filename'] + [url])
    except subprocess.CalledProcessError as cmd_error:
        text = "youtube-dl error: " + str(cmd_error.returncode) \
                            + " " + str(cmd_error.output)
        logging.error(text)
        bot.sendMessage(chat_id=update.message.chat_id, text=text)
    else:
        filename = out.decode("utf-8").rstrip('\n')
        logging.debug("filename: " + filename)
        directory = cfg['ydax_tmpdir']
        pathname = directory + '/' + filename
        try:
            out = subprocess.check_output(cmd \
                    + ['-x', '-q', '-o', pathname] + [url])
        except subprocess.CalledProcessError as cmd_error:
            text = "youtube-dl error: " + str(cmd_error.returncode) \
                                + " " + str(cmd_error.output)
            logging.error(text)
            bot.sendMessage(chat_id=update.message.chat_id, text=text)
        else:
            pattern = os.path.basename(filename)
            for audiofile in os.listdir(directory):
                if fnmatch.fnmatch(audiofile, pattern):
                    break
            logging.debug("sending: " + audiofile)
            audiopathname = directory + '/' + audiofile
            bot.sendAudio( chat_id=update.message.chat_id, 
                        audio=open(audiopathname, 'rb'),
                        title=audiofile)
            os.remove(audiopathname)            

###############
# Main section

# read configuration 
confload()

# setup logger
logging.info("Harpo start")

# setup telegram updater and  dispatchers
updater = Updater(token=cfg['bot']['token'])
dispatcher = updater.dispatcher

# begin telegram commands

# trace messages
trace_handler = MessageHandler(filter_any, lambda : True )
dispatcher.add_handler(trace_handler)

# ydax command
#ydax_handler = MessageHandler(Filters.entity(URL), ydax, pass_args=True )
class FilterYoutube(BaseFilter):
    def filter(self, message):
        return 'https://youtu.be/' in message.text
filter_youtube = FilterYoutube()
ydax_handler = MessageHandler(filter_youtube, ydax)
dispatcher.add_handler(ydax_handler)

# start command
confload_handler = CommandHandler('confload', confload)
dispatcher.add_handler(confload_handler)

# start command
start_handler = CommandHandler('start', start)
dispatcher.add_handler(start_handler)

# sincro command
sincro_handler = CommandHandler('sincro', sincro)
dispatcher.add_handler(sincro_handler)

# btc command
btc_handler = CommandHandler('btc', btc, pass_args=True)
dispatcher.add_handler(btc_handler)

# run updater 
updater.start_polling()
updater.idle()
logging.info("Harpo shutdown")

