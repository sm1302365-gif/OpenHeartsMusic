from hydrogram import filters, types

from OpenHeartsMusic import app, db


@app.on_message(filters.command(["vplaytoggle", "vplay_toggle"]) & app.sudo_filter)
async def vplay_toggle(_, m: types.Message) -> None:
	"""Enable or disable video playback commands globally."""
	if len(m.command) < 2 or m.command[1].lower() == "status":
		enabled = await db.get_vplay_enabled()
		status = "enabled" if enabled else "disabled"
		return await m.reply_text(
			f"<b>/vplay is currently {status}.</b>\n\n"
			"Usage: <code>/vplaytoggle enable</code> or "
			"<code>/vplaytoggle disable</code>"
		)

	action = m.command[1].lower()
	if action not in {"enable", "disable"}:
		return await m.reply_text(
			"Usage: <code>/vplaytoggle enable</code>, "
			"<code>/vplaytoggle disable</code>, or "
			"<code>/vplaytoggle status</code>"
		)

	enabled = action == "enable"
	await db.set_vplay_enabled(enabled)
	status = "enabled" if enabled else "disabled"
	await m.reply_text(f"✅ <b>/vplay has been {status} globally.</b>")
