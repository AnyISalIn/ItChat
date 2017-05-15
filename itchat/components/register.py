import logging, traceback, sys, threading, time, datetime
try:
    import Queue
except ImportError:
    import queue as Queue

from ..log import set_logging
from ..utils import test_connect, parse_date, is_holiday
from ..storage import templates

logger = logging.getLogger('itchat')

def load_register(core):
    core.auto_login       = auto_login
    core.configured_reply = configured_reply
    core.time_msg_register = time_msg_register
    core.send_time_msg = send_time_msg
    core.msg_register     = msg_register
    core.run              = run

def auto_login(self, hotReload=False, statusStorageDir='itchat.pkl',
        enableCmdQR=False, picDir=None, qrCallback=None,
        loginCallback=None, exitCallback=None):
    if not test_connect():
        logger.info("You can't get access to internet or wechat domain, so exit.")
        sys.exit()
    self.useHotReload = hotReload
    self.hotReloadDir = statusStorageDir
    if hotReload:
        if self.load_login_status(statusStorageDir,
                loginCallback=loginCallback, exitCallback=exitCallback):
            return
        self.login(enableCmdQR=enableCmdQR, picDir=picDir, qrCallback=qrCallback,
            loginCallback=loginCallback, exitCallback=exitCallback)
        self.dump_login_status(statusStorageDir)
    else:
        self.login(enableCmdQR=enableCmdQR, picDir=picDir, qrCallback=qrCallback,
            loginCallback=loginCallback, exitCallback=exitCallback)

def configured_reply(self):
    ''' determine the type of message and reply if its method is defined
        however, I use a strange way to determine whether a msg is from massive platform
        I haven't found a better solution here
        The main problem I'm worrying about is the mismatching of new friends added on phone
        If you have any good idea, pleeeease report an issue. I will be more than grateful.
    '''
    try:
        msg = self.msgList.get(timeout=1)
    except Queue.Empty:
        pass
    else:
        if isinstance(msg['User'], templates.User):
            replyFn = self.functionDict['FriendChat'].get(msg['Type'])
        elif isinstance(msg['User'], templates.MassivePlatform):
            replyFn = self.functionDict['MpChat'].get(msg['Type'])
        elif isinstance(msg['User'], templates.Chatroom):
            replyFn = self.functionDict['GroupChat'].get(msg['Type'])
        if replyFn is None:
            r = None
        else:
            try:
                r = replyFn(msg)
                if r is not None:
                    self.send(r, msg.get('FromUserName'))
            except:
                logger.warning(traceback.format_exc())

def send_time_msg(self, start_time):
    def send_to_usernames(func, usernames):
        r = func()
        for user in usernames:
            self.send(r, user)

    for func, info in self.timeDict.items():
        second, date, ok, usernames = info['second'], info['time']['date'], info['time']['ok'], info['to_usernames']
        try:
            if second:
                total_time = time.time() - start_time
                if total_time > info['second']:
                    send_to_usernames(func, usernames)
            elif date:
                now_d = datetime.datetime.now()
                if now_d > date and int((now_d - date).total_seconds()) < 600 and not ok:
                    send_to_usernames(func, usernames)
                    info['time']['ok'] = True
                elif now_d > date and int((now_d - date).total_seconds()) > 600 and ok:
                    info['time']['ok'] = False
        except:
            logger.warning(traceback.format_exc())



def msg_register(self, msgType, isFriendChat=False, isGroupChat=False, isMpChat=False):
    ''' a decorator constructor
        return a specific decorator based on information given '''
    if not (isinstance(msgType, list) or isinstance(msgType, tuple)):
        msgType = [msgType]
    def _msg_register(fn):
        for _msgType in msgType:
            if isFriendChat:
                self.functionDict['FriendChat'][_msgType] = fn
            if isGroupChat:
                self.functionDict['GroupChat'][_msgType] = fn
            if isMpChat:
                self.functionDict['MpChat'][_msgType] = fn
            if not any((isFriendChat, isGroupChat, isMpChat)):
                self.functionDict['FriendChat'][_msgType] = fn
        return fn
    return _msg_register

def time_msg_register(self, second=None, hour=None, min=None, usernames=None):
    usernames = usernames or []
    date = None if not hour or not min else parse_date(hour, min)
    second = None if hour else second
    def wrapper(fn):
        self.timeDict[fn] = {'second': second, 'time': {'date': date, 'ok': False}, 'to_usernames': usernames}
        return fn
    return wrapper

def run(self, debug=False, blockThread=True):
    start_time = time.time()
    logger.info('Start auto replying.')
    if debug:
        set_logging(loggingLevel=logging.DEBUG)
    def reply_fn():
        try:
            while self.alive:
                self.configured_reply()
                self.send_time_msg(start_time)
        except KeyboardInterrupt:
            if self.useHotReload:
                self.dump_login_status()
            self.alive = False
            logger.debug('itchat received an ^C and exit.')
            logger.info('Bye~')
    if blockThread:
        reply_fn()
    else:
        replyThread = threading.Thread(target=reply_fn)
        replyThread.setDaemon(True)
        replyThread.start()
