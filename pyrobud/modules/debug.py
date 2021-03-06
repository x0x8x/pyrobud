import inspect
import json
import logging
import re
from datetime import datetime
import telethon as tg
from .. import command, module, util


class DebugModule(module.Module):
    name = "Debug"

    @command.desc("Time `1 + 1`")
    async def cmd_time11(self, msg):
        reps = 1000000

        before = util.time.usec()
        for _ in range(reps):
            _ = 1 + 1
        after = util.time.usec()

        el_us = (after - before) / reps
        return "`1 + 1`: %.0f ns" % (el_us * 1000)

    @command.desc("Evaluate code")
    @command.alias("ev", "exec")
    @command.error_level(logging.WARNING)
    async def cmd_eval(self, msg, raw_args):
        code = util.tg.filter_code_block(raw_args)
        if not code:
            return "__I need code to execute.__"

        # Adapted from https://stackoverflow.com/a/53255739
        async def _eval(code):
            # Retrieve final expression's values
            lines = code.split("\n")
            if not lines[-1].startswith("return"):
                # Remove awaits from last line for the expression check
                lline = lines[-1].replace("await ", "")

                # Determine whether last line is a statement or expression
                try:
                    _ = compile(lline, "<stdin>", "eval")
                    is_expr = True
                except SyntaxError:
                    is_expr = False

                # If it is, prepend "return" to retrieve the value
                if is_expr:
                    lines[-1] = "return " + lines[-1]

            # Indent code to make it syntactically valid when injected into the function
            indented_code = "".join(f"\n    {line}" for line in lines)

            # Make an async function with the code and `exec` it
            exec(
                f"""
async def payload(self, msg, raw_args):
    # Inject send helper
    async def send(text):
        return await msg.respond(text)

    {indented_code}
"""
            )

            # Get `payload` from local variables, call it and return the result
            return await locals()["payload"](self, msg, raw_args)

        before = util.time.usec()
        result = await _eval(code)
        after = util.time.usec()

        el_us = after - before
        el_str = util.time.format_duration_us(el_us)

        return f"""```{str(result)}```

Time: {el_str}"""

    @command.desc("Get the code of a command")
    async def cmd_src(self, msg, cmd_name):
        if cmd_name is None or len(cmd_name) < 1:
            return "__Command name required to get source code.__"
        if cmd_name not in self.bot.commands:
            return f"__Command__ `{cmd_name}` __doesn't exist.__"

        src = await util.run_sync(lambda: inspect.getsource(self.bot.commands[cmd_name].func))
        filtered_src = re.sub(r"^    ", "", src, flags=re.MULTILINE)
        return f"```{filtered_src}```"

    @command.desc("Get plain text of a message")
    @command.alias("text", "raw")
    async def cmd_gtx(self, msg):
        if not msg.is_reply:
            return "__Reply to a message to get the text of.__"

        reply_msg = await msg.get_reply_message()
        await msg.result(reply_msg.text, parse_mode=None)

    @command.desc("Send text")
    async def cmd_echo(self, msg, text):
        if not text:
            return "__Provide text to send.__"

        return text

    @command.desc("Dump all the data of a message")
    @command.alias("md", "msginfo", "minfo")
    async def cmd_mdump(self, msg):
        if not msg.is_reply:
            return "__Reply to a message to get its data.__"

        reply_msg = await msg.get_reply_message()
        data = reply_msg.stringify()

        return f"```{data}```"

    @command.desc("Send media by file ID")
    @command.alias("file")
    async def cmd_fileid(self, msg, file_id):
        if not file_id and not msg.is_reply:
            return "__Provide a file ID to send or reply to a message with media to get its ID.__"

        if file_id:
            reply_msg = await msg.get_reply_message() if msg.is_reply else None

            await msg.result("Sending media...")
            await msg.respond(reply_to=reply_msg, file=file_id)
            await msg.delete()
        else:
            rep = await msg.get_reply_message()
            if not rep.media:
                return "__Provide a file ID to send or reply to a message with media to get its ID.__"

            if msg.file:
                return f"File ID: `{msg.file.id}`"

            return "__No compatible media found.__"

    @command.desc("Get all available information about the given entity (or `chat`)")
    @command.alias("einfo")
    async def cmd_entity(self, msg, entity_str):
        if entity_str == "chat":
            entity = await msg.get_chat()
        elif entity_str:
            if entity_str.isdigit():
                try:
                    entity_str = int(entity_str)
                except ValueError:
                    return f"Unable to parse `{entity_str}` as ID!"

            try:
                entity = await self.bot.client.get_entity(entity_str)
            except ValueError as e:
                return f"Error getting entity `{entity_str}`: {e}"
        elif msg.is_reply:
            entity = await msg.get_reply_message()
        else:
            return "__No entity given via argument or reply.__"
        return f"```{entity.stringify()}```"

    @command.desc("Get all contextually relevant IDs")
    @command.alias("user", "info")
    async def cmd_id(self, msg):
        global f_chat_id, f_msg_id
        lines = []

        if msg.chat_id:
            lines.append(f"Chat ID: `{msg.chat_id}`")

        lines.append(f"My user ID: `{self.bot.uid}`")

        if msg.is_reply:
            reply_msg = await msg.get_reply_message()
            sender = await reply_msg.get_sender()
            lines.append(f"Message ID: `{reply_msg.id}`")

            if sender:
                lines.append(f"Message author ID: `{sender.id}`")

            if reply_msg.forward:
                lines.append(f"Forwarded message author ID: `{reply_msg.forward.sender.id}`")
                """
                forward_dir = dir(reply_msg.forward)
                for fd in forward_dir:
                    evaled = ""
                    try: evaled = str(eval(fd))
                    except: evaled = "Error"
                    print(fd, evaled)
                """
                if reply_msg.forward.chat:
                    lines.append(f"Forwarded message chat ID: `{reply_msg.forward.chat.id}`")

                if reply_msg.forward.saved_from_msg_id:
                    lines.append(f"Forwarded message's original ID: `{reply_msg.forward.saved_from_msg_id}`")
                if reply_msg.forward.from_id:
                    lines.append(f"Forwarded message author ID: `{reply_msg.forward.from_id}`")

                if hasattr(reply_msg.forward.saved_from_peer, "channel_id"):
                    f_chat_id = reply_msg.forward.saved_from_peer.channel_id
                    lines.append(f"Forwarded message chat ID: `{f_chat_id}`")

                if reply_msg.forward.saved_from_msg_id:
                    f_msg_id = reply_msg.forward.saved_from_msg_id
                    lines.append(f"Forwarded message original ID: `{f_msg_id}`")

                if reply_msg.forward.saved_from_peer and reply_msg.forward.saved_from_msg_id:
                    lines.append(f"[Link to forwarded message](https://t.me/c/{f_chat_id}/{f_msg_id})")

        return "\n".join(lines)

    """
    @command.desc("Get user infos by ID")
    async def cmd_getuser(self, msg: tg.events.newmessage, input_user: str):
        input_user = util.sanitize(input_user)
        if input_user.isdigit(): input_user = int(input_user)
        try:
            user = await self.bot.client.get_entity(input_user)
            await msg.respond(util.UserStr(user), reply_to=msg.reply_to_msg_id)
        except ValueError:
            await msg.respond(f"Could not find any user matching `{input_user}`!", reply_to=msg.reply_to_msg_id)
        await msg.delete()
    """

    @command.desc("List all chats with IDs")
    async def cmd_listchats(self, msg: tg.events.newmessage):
        dialogs = await self.bot.client.get_dialogs()
        lines = [f"**{len(dialogs)} Chats:**\n"]
        await msg.respond(lines[0])
        for dialog in dialogs: lines.append(util.bluscream.ChatStr(dialog))
        await msg.delete()
        msgs = util.bluscream.splitMsg("\n".join(lines))
        # await msg.respond(msgs[0])
        for message in msgs: await msg.respond(message)

    @command.desc("Get recent actions of a chat")
    @command.alias("actions")
    async def cmd_recentactions(self, msg: tg.events.newmessage, input_chat: str = None):
        await msg.result("Collecting recent actions...")
        log_items = list()
        async for event in self.bot.client.iter_admin_log(input_chat if input_chat else msg.to_id):
            event = event.stringify().replace("\n", " ")
            log_items.append(f"```\n{event}\n```")
        msgs = util.bluscream.splitMsg("\n".join(log_items))
        for message in msgs: await msg.respond(message)

    @command.desc("Get information about pyrobud")
    @command.alias("bi")
    async def cmd_botinfo(self, msg, localtime: bool = True):
        if msg is not None: await msg.result("Collecting bot information...")
        botinfo = list()
        botinfo.append(f"Bot: @pyrobud ({util.version.get_commit()})")
        botinfo.append(f"User: @{self.bot.user.username} ({self.bot.uid})")
        botinfo.append(f"Telethon v`{tg.__version__}`")
        if localtime: botinfo.append(f"Local Time: `{datetime.now()}`")
        botinfo.append(f"Starttime: `{self.bot.start_time}`")
        botinfo.append(f"Uptime: `{datetime.utcnow() - self.bot.start_time}`")
        # botinfo.append(f"Uptime: {util.format_duration_us(self.bot.start_time_us)}")
        return "\n".join(botinfo)
