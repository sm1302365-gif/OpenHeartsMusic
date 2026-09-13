# ==============================================================================
# restart.py - System Controls
# ==============================================================================
# Commands for grabbing logs and rebooting the bot.
# ==============================================================================

import os
import sys
import shutil
import asyncio

from hydrogram import filters, types

from OpenHeartsMusic import app, db, lang, stop


@app.on_message(filters.command(["logs"]) & app.sudo_filter)
@lang.language()
async def _logs(_, m: types.Message):
    # Auto-delete command message
    try:
        await m.delete()
    except Exception:
        pass

    sent = await m.reply_text(m.lang["log_fetch"])
    if not os.path.exists("log.txt"):
        return await sent.edit_text(m.lang["log_not_found"])

    try:
        with open("log.txt", "r", encoding="utf-8") as f:
            content = f.read()

        start_marker = "📁 Cache directories updated."
        last_start_index = content.rfind(start_marker)

        if last_start_index != -1:
            recent_logs = content[last_start_index:]
            temp_log_path = "temp_recent_logs.txt"
            with open(temp_log_path, "w", encoding="utf-8") as f:
                f.write(recent_logs)

            try:
                await sent.delete()
            except Exception:
                pass

            await m.reply_document(
                document=temp_log_path,
                caption=m.lang["log_sent"].format(app.name) + " (Last session)",
                quote=False,
            )

            try:
                os.remove(temp_log_path)
            except Exception:
                pass
        else:
            try:
                await sent.delete()
            except Exception:
                pass

            await m.reply_document(
                document="log.txt",
                caption=m.lang["log_sent"].format(app.name),
                quote=False,
            )
    except Exception as e:
        await sent.edit_text(f"Error reading logs: {str(e)}")


@app.on_message(filters.command(["logger"]) & app.sudo_filter)
@lang.language()
async def _logger(_, m: types.Message):
    # Auto-delete command message
    try:
        await m.delete()
    except Exception:
        pass

    if len(m.command) < 2:
        return await m.reply_text(m.lang["logger_usage"].format(m.command[0]))
    if m.command[1] not in ("on", "off"):
        return await m.reply_text(m.lang["logger_usage"].format(m.command[0]))

    if m.command[1] == "on":
        await db.set_logger(True)
        await m.reply_text(m.lang["logger_on"])
    else:
        await db.set_logger(False)
        await m.reply_text(m.lang["logger_off"])


@app.on_message(filters.command(["restart"]) & app.sudo_filter)
@lang.language()
async def _restart(_, m: types.Message):
    # Auto-delete command message
    try:
        await m.delete()
    except Exception:
        pass

    sent = await m.reply_text(m.lang["restarting"])

    # Keep downloads to allow instant reuse after restart.
    for directory in ["cache"]:
        shutil.rmtree(directory, ignore_errors=True)

    await sent.edit_text(m.lang["restarted"])
    task = asyncio.create_task(stop())
    task.add_done_callback(lambda t: None if t.cancelled() else t.exception())
    await asyncio.sleep(2)

    os.execl(sys.executable, sys.executable, "-m", "OpenHeartsMusic")
