"""Translations of the texts Python writes (see i18n.py). Key: the English text, exactly as in the source.

Every entry has all four languages and the same placeholders in the same order as its key. Words for shared terms
are OrcaSlicer's own (toolhead, nozzle, bed, preset, time-lapse). German is formal ("Sie"), Spanish neutral, Chinese
uses its own punctuation. Text from the printer, Spoolman or the system fills the placeholders as it came.
"""


def _m(pt, es, de, zh):
    return {"pt-BR": pt, "es": es, "de": de, "zh-CN": zh}


MESSAGES = {
    "U1 print setup already done for this G-code; nothing sent again": _m(
        "o preparo da impressão na U1 já foi feito para este G-code; nada foi enviado de novo",
        "la preparación de impresión de la U1 ya se hizo para este G-Code; no se envió nada de nuevo",
        "die U1-Druckvorbereitung wurde für diesen G-Code bereits ausgeführt; es wurde nichts erneut gesendet",
        "此 G-code 已完成 U1 打印准备；未再次发送任何内容"),
    "unknown top-cover fan %r": _m("ventilador da tampa superior desconhecido: %r", "ventilador de la tapa superior desconocido: %r",
                                   "unbekannter Lüfter der oberen Abdeckung: %r", "未知的顶盖风扇：%r"),
    "not supported by this firmware": _m("não é compatível com este firmware", "no es compatible con este firmware",
                                         "wird von dieser Firmware nicht unterstützt", "此固件不支持"),
    # ------------------------------------------------------------ print setup after OrcaSlicer's Print
    "U1 Control — print setup": _m("U1 Control — preparo da impressão", "U1 Control — preparación de la impresión",
                                   "U1 Control — Druckvorbereitung", "U1 Control — 打印准备"),
    '%s. Turn on "Show print setup before sending" to choose toolheads.': _m(
        '%s. Ligue "Mostrar o preparo antes de enviar" para escolher as cabeças.',
        '%s. Active "Mostrar la preparación antes de enviar" para elegir los cabezales.',
        '%s. Schalten Sie „Druckvorbereitung vor dem Senden zeigen“ ein, um die Werkzeugköpfe zu wählen.',
        '%s。请打开“发送前显示打印准备”以选择工具头。'),
    "unknown command": _m("comando desconhecido", "comando desconocido", "unbekannter Befehl", "未知命令"),
    "open the U1 Control tab for this printer to change its toolheads": _m(
        "abra a aba U1 Control desta impressora para alterar as cabeças",
        "abra la pestaña U1 Control de esta impresora para cambiar sus cabezales",
        "öffnen Sie den Tab U1 Control für diesen Drucker, um seine Werkzeugköpfe zu ändern",
        "请打开此打印机的 U1 Control 标签页以更改工具头"),
    # ------------------------------------------------------------ printer agent (OrcaSlicer's Print dialog)
    "Preparing...": _m("Preparando...", "Preparando...", "Wird vorbereitet...", "正在准备..."),
    "Uploading G-code...": _m("Enviando o G-code...", "Subiendo el G-Code...", "G-Code wird hochgeladen...", "正在上传 G-code..."),
    "Starting print...": _m("Iniciando a impressão...", "Iniciando la impresión...", "Druck wird gestartet...", "正在开始打印..."),
    "File uploaded": _m("Arquivo enviado", "Archivo subido", "Datei hochgeladen", "文件已上传"),
    "Print started": _m("Impressão iniciada", "Impresión iniciada", "Druck gestartet", "打印已开始"),
    "Snapmaker U1 over Moonraker, by u1control": _m(
        "Snapmaker U1 via Moonraker, pelo u1control", "Snapmaker U1 mediante Moonraker, con u1control",
        "Snapmaker U1 über Moonraker, von u1control", "通过 Moonraker 连接 Snapmaker U1（u1control）"),
    "no G-code for plate %s in %s": _m(
        "não há G-code da placa %s em %s", "no hay G-Code de la cama %s en %s",
        "kein G-Code für Platte %s in %s", "找不到第 %s 盘的 G-code（文件 %s）"),
    "this G-code was not sliced for a Snapmaker U1": _m(
        "este G-code não foi fatiado para uma Snapmaker U1", "este G-Code no se laminó para una Snapmaker U1",
        "dieser G-Code wurde nicht für einen Snapmaker U1 gesliced", "此 G-code 不是为 Snapmaker U1 切片的"),
    "%s. Pick other slots in the print dialog, or load the filament.": _m(
        "%s. Escolha outros slots na janela de impressão ou carregue o filamento.",
        "%s. Elija otras ranuras en el diálogo de impresión o cargue el filamento.",
        "%s. Wählen Sie im Druckdialog andere Plätze oder laden Sie das Filament.",
        "%s。请在打印对话框中选择其他槽位，或先进料。"),
    "the U1 is busy (%s); wait for it to finish first": _m(
        "a U1 está ocupada (%s); espere ela terminar", "la U1 está ocupada (%s); espere a que termine",
        "der U1 ist beschäftigt (%s); warten Sie, bis er fertig ist", "U1 正忙（%s）；请等待其完成"),
    "the U1 is busy; wait for it to finish first": _m(
        "a U1 está ocupada; espere ela terminar", "la U1 está ocupada; espere a que termine",
        "der U1 ist beschäftigt; warten Sie, bis er fertig ist", "U1 正忙；请等待其完成"),
    "the U1 is printing %s now; send it under another name or wait": _m(
        "a U1 está imprimindo %s agora; envie com outro nome ou espere",
        "la U1 está imprimiendo %s ahora; envíelo con otro nombre o espere",
        "der U1 druckt gerade %s; senden Sie die Datei unter einem anderen Namen oder warten Sie",
        "U1 正在打印 %s；请换一个名称发送，或等待完成"),
    "%s; the file is on the U1, nothing was started": _m(
        "%s; o arquivo está na U1, nada foi iniciado", "%s; el archivo está en la U1, no se inició nada",
        "%s; die Datei liegt auf dem U1, es wurde nichts gestartet", "%s；文件已在 U1 上，未开始任何打印"),
    "T%d changed during the upload; the file is on the U1, nothing was started. Print again.": _m(
        "T%d mudou durante o envio; o arquivo está na U1, nada foi iniciado. Imprima de novo.",
        "T%d cambió durante la subida; el archivo está en la U1, no se inició nada. Imprima de nuevo.",
        "T%d hat sich während des Hochladens geändert; die Datei liegt auf dem U1, es wurde nichts gestartet. "
        "Drucken Sie erneut.",
        "T%d 在上传期间发生了变化；文件已在 U1 上，未开始任何打印。请重新打印。"),
    "no U1 address set: set the printer preset's host to the U1's IP": _m(
        "nenhum endereço da U1: defina o host do perfil de impressora com o IP da U1",
        "no hay dirección de la U1: ponga la IP de la U1 como host del perfil de impresora",
        "keine U1-Adresse festgelegt: tragen Sie die IP des U1 als Host im Druckerprofil ein",
        "未设置 U1 地址：请把打印机预设的主机设为 U1 的 IP"),

    # ------------------------------------------------------------ U1 print setup (slicing pipeline)
    "U1 print setup": _m("Preparar impressão na U1", "Preparación de impresión de la U1", "U1-Druckvorbereitung", "U1 打印准备"),
    "U1 print setup: cancelled, nothing was sent.": _m(
        "Preparo da impressão na U1: cancelado, nada foi enviado.",
        "Preparación de impresión de la U1: cancelada, no se envió nada.",
        "U1-Druckvorbereitung: abgebrochen, es wurde nichts gesendet.",
        "U1 打印准备：已取消，未发送任何内容。"),
    "U1 print setup: %s": _m("Preparo da impressão na U1: %s", "Preparación de impresión de la U1: %s",
                             "U1-Druckvorbereitung: %s", "U1 打印准备：%s"),
    "U1 print setup added to %s; save the preset to keep it": _m(
        "“U1 print setup” adicionado a %s; salve o perfil para manter",
        "«U1 print setup» añadido a %s; guarde el perfil para conservarlo",
        "„U1 print setup“ wurde zu %s hinzugefügt; speichern Sie das Profil, um es zu behalten",
        "已将“U1 print setup”添加到 %s；请保存预设以保留"),
    "not a Snapmaker U1 print; skipped": _m(
        "não é uma impressão para a Snapmaker U1; ignorado", "no es una impresión para la Snapmaker U1; omitido",
        "kein Druck für den Snapmaker U1; übersprungen", "不是 Snapmaker U1 的打印；已跳过"),
    "U1 G-code prepared (top cover: %s)": _m(
        "G-code da U1 preparado (tampa superior: %s)", "G-Code de la U1 preparado (cubierta superior: %s)",
        "U1-G-Code vorbereitet (obere Abdeckung: %s)", "U1 G-code 已准备好（顶盖：%s）"),
    "left as sliced": _m("como fatiado", "como se laminó", "wie beim Slicen festgelegt", "保持切片时的设置"),
    "keep warm": _m("manter aquecido", "mantener caliente", "warm halten", "保温"),
    "weak cooling": _m("resfriamento fraco", "enfriamiento suave", "schwache Kühlung", "弱冷却"),
    "strong cooling": _m("resfriamento forte", "enfriamiento fuerte", "starke Kühlung", "强冷却"),
    "sent to %s: %s": _m("enviado para %s: %s", "enviado a %s: %s", "an %s gesendet: %s", "已发送到 %s：%s"),
    "no U1 address set: click the Wi-Fi icon next to the printer and enter its IP": _m(
        "nenhum endereço da U1: clique no ícone de Wi-Fi ao lado da impressora e informe o IP",
        "no hay dirección de la U1: haga clic en el icono de Wi-Fi junto a la impresora e introduzca su IP",
        "keine U1-Adresse festgelegt: klicken Sie auf das WLAN-Symbol neben dem Drucker und geben Sie die IP ein",
        "未设置 U1 地址：请点击打印机旁的 Wi-Fi 图标并输入其 IP"),
    "print setup timed out; nothing was sent": _m(
        "o preparo da impressão expirou; nada foi enviado", "se agotó el tiempo de la preparación de la impresión; no se envió nada",
        "Zeitüberschreitung bei der Druckvorbereitung; es wurde nichts gesendet", "打印准备已超时；未发送任何内容"),
    "the print setup window didn't open (OrcaSlicer was busy); nothing was sent": _m(
        "a janela de preparo da impressão não abriu (o OrcaSlicer estava ocupado); nada foi enviado",
        "la ventana de preparación de la impresión no se abrió (OrcaSlicer estaba ocupado); no se envió nada",
        "das Fenster der Druckvorbereitung wurde nicht geöffnet (OrcaSlicer war beschäftigt); es wurde nichts gesendet",
        "打印准备窗口未能打开（OrcaSlicer 正忙）；未发送任何内容"),
    "the print setup has warnings (%s) that weren't confirmed for these toolheads; nothing was sent": _m(
        "o preparo da impressão tem avisos (%s) que não foram confirmados para estas cabeças; nada foi enviado",
        "la preparación de la impresión tiene advertencias (%s) sin confirmar para estos cabezales; no se envió nada",
        "die Druckvorbereitung hat Warnungen (%s), die für diese Werkzeugköpfe nicht bestätigt wurden; "
        "es wurde nichts gesendet",
        "打印准备中有警告（%s）尚未针对这些工具头确认；未发送任何内容"),
    "the printer address changed while the print setup was open; nothing was sent": _m(
        "o endereço da impressora mudou com o preparo da impressão aberto; nada foi enviado",
        "la dirección de la impresora cambió con la preparación de la impresión abierta; no se envió nada",
        "die Druckeradresse hat sich geändert, während die Druckvorbereitung geöffnet war; es wurde nichts gesendet",
        "打印准备窗口打开期间打印机地址发生了变化；未发送任何内容"),
    "the U1 became busy (%s); nothing was sent": _m(
        "a U1 ficou ocupada (%s); nada foi enviado", "la U1 pasó a estar ocupada (%s); no se envió nada",
        "der U1 ist inzwischen beschäftigt (%s); es wurde nichts gesendet", "U1 已变为忙碌（%s）；未发送任何内容"),
    "T%d changed after you chose the toolheads; nothing was sent. Send again.": _m(
        "T%d mudou depois que você escolheu as cabeças; nada foi enviado. Envie de novo.",
        "T%d cambió después de elegir los cabezales; no se envió nada. Envíe de nuevo.",
        "T%d hat sich geändert, nachdem Sie die Werkzeugköpfe gewählt haben; es wurde nichts gesendet. "
        "Senden Sie erneut.",
        "选择工具头之后 T%d 发生了变化；未发送任何内容。请重新发送。"),
    "Filament %d → T%d: toolhead is empty": _m(
        "Filamento %d → T%d: a cabeça está vazia", "Filamento %d → T%d: el cabezal está vacío",
        "Filament %d → T%d: Der Werkzeugkopf ist leer", "耗材丝 %d → T%d：工具头为空"),
    "Filament %d (%s) → T%d loaded with %s": _m(
        "Filamento %d (%s) → T%d carregada com %s", "Filamento %d (%s) → T%d cargado con %s",
        "Filament %d (%s) → T%d ist mit %s geladen", "耗材丝 %d（%s）→ T%d 装的是 %s"),

    # ------------------------------------------------------------ U1 Control tab: selection and notices
    "the U1 did not answer in %d s": _m("a U1 não respondeu em %d s", "la U1 no respondió en %d s",
                                        "der U1 hat nicht innerhalb von %d s geantwortet", "U1 在 %d 秒内没有应答"),
    "Select a Snapmaker U1 printer, or set \"host\" in U1 Control's plugin config.": _m(
        "Selecione uma impressora Snapmaker U1 ou defina \"host\" na configuração do plugin U1 Control.",
        "Seleccione una impresora Snapmaker U1 o defina «host» en la configuración del plugin U1 Control.",
        "Wählen Sie einen Snapmaker-U1-Drucker oder legen Sie „host“ in der Plugin-Konfiguration von U1 Control fest.",
        "请选择一台 Snapmaker U1 打印机，或在 U1 Control 的插件配置中设置“host”。"),
    "The selected U1 has no address: click the Wi-Fi icon next to the printer and enter its IP.": _m(
        "A U1 selecionada não tem endereço: clique no ícone de Wi-Fi ao lado da impressora e informe o IP.",
        "La U1 seleccionada no tiene dirección: haga clic en el icono de Wi-Fi junto a la impresora e introduzca su IP.",
        "Der gewählte U1 hat keine Adresse: Klicken Sie auf das WLAN-Symbol neben dem Drucker und geben Sie die IP ein.",
        "所选的 U1 没有地址：请点击打印机旁的 Wi-Fi 图标并输入其 IP。"),
    "Spooler is keeping slots synced": _m(
        "O Spooler está mantendo os slots sincronizados", "Spooler mantiene las ranuras sincronizadas",
        "Spooler hält die Plätze synchron", "Spooler 正在保持槽位同步"),
    "No printer status yet; try again in a moment.": _m(
        "Ainda não há status da impressora; tente de novo em instantes.",
        "Aún no hay estado de la impresora; inténtelo de nuevo en un momento.",
        "Noch kein Druckerstatus; versuchen Sie es gleich noch einmal.", "尚无打印机状态；请稍后再试。"),
    "Couldn't update the project filaments: %s": _m(
        "Não foi possível atualizar os filamentos do projeto: %s",
        "No se pudieron actualizar los filamentos del proyecto: %s",
        "Die Filamente des Projekts konnten nicht aktualisiert werden: %s", "无法更新项目耗材丝：%s"),
    "Another preset update is running; try again in a moment.": _m(
        "Outra atualização de perfil está em andamento; tente de novo em instantes.",
        "Hay otra actualización de perfil en curso; inténtelo de nuevo en un momento.",
        "Eine andere Profiländerung läuft noch; versuchen Sie es gleich noch einmal.",
        "另一项预设更新正在进行；请稍后再试。"),
    "Project filaments %s": _m("Filamentos do projeto %s", "Filamentos del proyecto %s", "Projektfilamente %s", "项目耗材丝：%s"),
    "unchanged": _m("sem alterações", "sin cambios", "unverändert", "未更改"),
    ". Problems: %s": _m(". Problemas: %s", ". Problemas: %s", ". Probleme: %s", "。问题：%s"),
    "filament %d: %s": _m("filamento %d: %s", "filamento %d: %s", "Filament %d: %s", "耗材丝 %d：%s"),
    "T%d: no compatible user preset \"%s\" in OrcaSlicer, so the usual preset is used": _m(
        "T%d: não há perfil de usuário compatível “%s” no OrcaSlicer, então foi usado o perfil de sempre",
        "T%d: no hay ningún perfil de usuario compatible «%s» en OrcaSlicer, así que se usa el perfil habitual",
        "T%d: kein kompatibles Benutzerprofil „%s“ in OrcaSlicer, daher wird das übliche Profil verwendet",
        "T%d：OrcaSlicer 中没有兼容的用户预设“%s”，因此使用常规预设"),
    "T%d: several user presets match \"%s\" ignoring case; write the exact name. The usual preset is used": _m(
        "T%d: vários perfis de usuário correspondem a “%s” sem diferenciar maiúsculas; escreva o nome exato. Foi usado o perfil de sempre",
        "T%d: varios perfiles de usuario coinciden con «%s» sin distinguir mayúsculas; escriba el nombre exacto. Se usa el perfil habitual",
        "T%d: mehrere Benutzerprofile passen zu „%s“, wenn man Groß-/Kleinschreibung ignoriert; geben Sie den genauen Namen ein. Das übliche Profil wird verwendet",
        "T%d：有多个用户预设在忽略大小写时与“%s”匹配；请填写准确名称。将使用常规预设"),

    # ------------------------------------------------------------ helper scripts
    "Select your Snapmaker U1 printer and set its IP (Wi-Fi icon next to the printer).": _m(
        "Selecione sua impressora Snapmaker U1 e defina o IP (ícone de Wi-Fi ao lado da impressora).",
        "Seleccione su impresora Snapmaker U1 y defina su IP (icono de Wi-Fi junto a la impresora).",
        "Wählen Sie Ihren Snapmaker-U1-Drucker und legen Sie seine IP fest (WLAN-Symbol neben dem Drucker).",
        "请选择您的 Snapmaker U1 打印机并设置其 IP（打印机旁的 Wi-Fi 图标）。"),
    "Couldn't reach the U1: %s": _m("Não foi possível alcançar a U1: %s", "No se pudo conectar con la U1: %s",
                                    "Der U1 ist nicht erreichbar: %s", "无法连接 U1：%s"),
    "OrcaSlicer did not answer in time; try again": _m("O OrcaSlicer não respondeu a tempo; tente de novo",
                                                       "OrcaSlicer no respondió a tiempo; inténtelo de nuevo",
                                                       "OrcaSlicer hat nicht rechtzeitig geantwortet; versuchen Sie es erneut",
                                                       "OrcaSlicer 未及时响应；请重试"),
    "U1 at %s (official firmware %s)": _m("U1 em %s (firmware oficial %s)", "U1 en %s (firmware oficial %s)",
                                          "U1 unter %s (offizielle Firmware %s)", "U1 位于 %s（官方固件 %s）"),
    "U1 at %s (Extended Firmware %s)": _m("U1 em %s (Extended Firmware %s)", "U1 en %s (Extended Firmware %s)",
                                          "U1 unter %s (Extended Firmware %s)", "U1 位于 %s（Extended Firmware %s）"),
    "empty": _m("vazia", "vacío", "leer", "空"),
    "Select a Snapmaker U1 printer first.": _m(
        "Selecione primeiro uma impressora Snapmaker U1.", "Seleccione primero una impresora Snapmaker U1.",
        "Wählen Sie zuerst einen Snapmaker-U1-Drucker.", "请先选择一台 Snapmaker U1 打印机。"),
    "\"%s\" already matches Snapmaker Orca.": _m(
        "\"%s\" já corresponde ao Snapmaker Orca.", "«%s» ya coincide con Snapmaker Orca.",
        "„%s“ entspricht bereits Snapmaker Orca.", "“%s”已与 Snapmaker Orca 一致。"),
    "Change the process preset \"%s\" to Snapmaker Orca's U1 values?\n\n%s\n\n"
    "The preset stays unsaved until you save it.": _m(
        "Alterar o perfil de processo \"%s\" para os valores do Snapmaker Orca para a U1?\n\n%s\n\n"
        "O perfil fica sem salvar até você salvá-lo.",
        "¿Cambiar el perfil de proceso «%s» a los valores de Snapmaker Orca para la U1?\n\n%s\n\n"
        "El perfil queda sin guardar hasta que lo guarde.",
        "Das Prozessprofil „%s“ auf die U1-Werte von Snapmaker Orca umstellen?\n\n%s\n\n"
        "Das Profil bleibt ungespeichert, bis Sie es speichern.",
        "把工艺预设“%s”改为 Snapmaker Orca 的 U1 数值？\n\n%s\n\n在您保存之前，预设保持未保存状态。"),
    "No changes made.": _m("Nada foi alterado.", "No se hicieron cambios.", "Es wurde nichts geändert.", "未做任何更改。"),
    "Updated %d setting(s); save the preset to keep them.": _m(
        "%d ajuste(s) atualizado(s); salve o perfil para manter.",
        "%d ajuste(s) actualizado(s); guarde el perfil para conservarlos.",
        "%d Einstellung(en) geändert; speichern Sie das Profil, um sie zu behalten.",
        "已更新 %d 项设置；请保存预设以保留。"),

    # ------------------------------------------------------------ commands from the tab (service)
    "the selected printer changed; nothing was sent to it": _m(
        "a impressora selecionada mudou; nada foi enviado a ela",
        "la impresora seleccionada cambió; no se le envió nada",
        "der gewählte Drucker hat gewechselt; es wurde nichts an ihn gesendet", "所选打印机已更改；未向其发送任何内容"),
    "no U1 selected: choose a Snapmaker U1 printer with an address": _m(
        "nenhuma U1 selecionada: escolha uma impressora Snapmaker U1 com endereço",
        "ninguna U1 seleccionada: elija una impresora Snapmaker U1 con dirección",
        "kein U1 gewählt: Wählen Sie einen Snapmaker-U1-Drucker mit Adresse",
        "未选择 U1：请选择一台带地址的 Snapmaker U1 打印机"),
    "too many thumbnails waiting": _m("há miniaturas demais na fila", "hay demasiadas miniaturas en espera",
                                      "zu viele Vorschaubilder in der Warteschlange", "等待中的缩略图过多"),
    "unknown command %s": _m("comando desconhecido %s", "comando desconocido %s", "unbekannter Befehl %s", "未知命令 %s"),
    "%s failed: %s": _m("%s falhou: %s", "%s falló: %s", "%s fehlgeschlagen: %s", "%s 失败：%s"),
    "camera returned no image": _m("a câmera não devolveu imagem", "la cámara no devolvió ninguna imagen",
                                   "die Kamera hat kein Bild geliefert", "摄像头没有返回图像"),
    "no recent camera picture: start the camera first": _m(
        "não há imagem recente da câmera: inicie a câmera primeiro",
        "no hay imagen reciente de la cámara: inicie primero la cámara",
        "kein aktuelles Kamerabild: Starten Sie zuerst die Kamera", "没有最近的摄像头画面：请先启动摄像头"),
    "remote screen is off: turn on Remote Screen in Settings > Firmware": _m(
        "a tela remota está desligada: ligue Remote Screen em Ajustes > Firmware",
        "la pantalla remota está apagada: active Remote Screen en Ajustes > Firmware",
        "der Remote-Bildschirm ist aus: Schalten Sie Remote Screen unter Einstellungen > Firmware ein",
        "远程屏幕已关闭：请在 设置 > 固件 中开启 Remote Screen"),
    "T%d now uses Spoolman spool #%d (%s %s)": _m(
        "T%d agora usa a bobina #%d do Spoolman (%s %s)", "T%d usa ahora la bobina #%d de Spoolman (%s %s)",
        "T%d verwendet jetzt die Spoolman-Spule #%d (%s %s)", "T%d 现在使用 Spoolman 料盘 #%d（%s %s）"),
    "T%d now shows that filament, but Spoolman did not record spool #%d on T%d (%s); links reloaded from Spoolman": _m(
        "T%d já mostra esse filamento, mas o Spoolman não registrou a bobina #%d em T%d (%s); vínculos recarregados "
        "do Spoolman",
        "T%d ya muestra ese filamento, pero Spoolman no registró la bobina #%d en T%d (%s); asignaciones recargadas "
        "desde Spoolman",
        "T%d zeigt dieses Filament jetzt an, aber Spoolman hat die Spule #%d an T%d nicht eingetragen (%s); "
        "Zuweisungen wurden aus Spoolman neu geladen",
        "T%d 已显示该耗材丝，但 Spoolman 未记录料盘 #%d 在 T%d 上（%s）；已从 Spoolman 重新加载绑定"),
    "Spoolman did not record spool #%d on T%d (%s); links reloaded from Spoolman": _m(
        "O Spoolman não registrou a bobina #%d em T%d (%s); vínculos recarregados do Spoolman",
        "Spoolman no registró la bobina #%d en T%d (%s); asignaciones recargadas desde Spoolman",
        "Spoolman hat die Spule #%d an T%d nicht eingetragen (%s); Zuweisungen wurden aus Spoolman neu geladen",
        "Spoolman 未记录料盘 #%d 在 T%d 上（%s）；已从 Spoolman 重新加载绑定"),
    "spool #%d is linked to T%d, but spool #%d still lists T%d in Spoolman (%s); clear its location there": _m(
        "a bobina #%d está vinculada a T%d, mas a bobina #%d ainda aparece em T%d no Spoolman (%s); "
        "limpe a localização dela lá",
        "la bobina #%d está asignada a T%d, pero la bobina #%d sigue figurando en T%d en Spoolman (%s); "
        "borre allí su ubicación",
        "Spule #%d ist T%d zugewiesen, aber Spule #%d steht in Spoolman noch auf T%d (%s); "
        "löschen Sie dort ihren Lagerort",
        "料盘 #%d 已绑定到 T%d，但料盘 #%d 在 Spoolman 中仍显示在 T%d（%s）；请在那里清除它的位置"),
    "empty command": _m("comando vazio", "comando vacío", "leerer Befehl", "命令为空"),
    "printer replies unavailable (%s)": _m(
        "respostas da impressora indisponíveis (%s)", "respuestas de la impresora no disponibles (%s)",
        "Antworten des Druckers nicht verfügbar (%s)", "无法获取打印机的回复（%s）"),
    "replies the printer logged since this command; other clients' messages can show up too": _m(
        "respostas que a impressora registrou desde este comando; mensagens de outros clientes também podem aparecer",
        "respuestas que la impresora registró desde este comando; también pueden aparecer mensajes de otros clientes",
        "Antworten, die der Drucker seit diesem Befehl protokolliert hat; Meldungen anderer Clients können auch erscheinen",
        "打印机自此命令以来记录的回复；也可能出现其他客户端的消息"),
    "unexpected gcode store answer": _m(
        "resposta inesperada do registro de G-code", "respuesta inesperada del registro de G-Code",
        "unerwartete Antwort des G-Code-Speichers", "G-code 记录返回了意外的应答"),
    "bad purifier mode": _m("modo de tampa superior inválido", "modo de cubierta superior no válido",
                            "ungültiger Modus der oberen Abdeckung", "顶盖模式无效"),
    "Unload when done is chosen for each print, per toolhead, in the U1 print setup pop-up": _m(
        "Descarregar ao terminar é escolhido a cada impressão, por cabeça, na janela de preparo da impressão na U1",
        "Descargar al terminar se elige en cada impresión, por cabezal, en la ventana de preparación de impresión de la U1",
        "Entladen nach dem Druck wird für jeden Druck je Werkzeugkopf im Fenster der U1-Druckvorbereitung gewählt",
        "“完成后退料”需在 U1 打印准备窗口中按每次打印、每个工具头选择"),
    "The exhaust fan stays off while the top cover recirculates (keep warm)": _m(
        "O exaustor fica desligado enquanto a tampa superior recircula o ar (manter aquecido)",
        "El extractor se queda apagado mientras la cubierta superior recircula el aire (mantener caliente)",
        "Der Abluftlüfter bleibt aus, solange die obere Abdeckung die Luft umwälzt (warm halten)",
        "顶盖内循环（保温）时排风扇保持关闭"),
    "nothing to change": _m("nada a alterar", "nada que cambiar", "nichts zu ändern", "没有可更改的内容"),
    "touch outside the screen": _m("toque fora da tela", "el toque está fuera de la pantalla",
                                   "Berührung außerhalb des Bildschirms", "点击位置超出屏幕"),
    "the U1 is busy (%s)": _m("a U1 está ocupada (%s)", "la U1 está ocupada (%s)", "der U1 ist beschäftigt (%s)", "U1 正忙（%s）"),
    "unknown calibration": _m("calibração desconhecida", "calibración desconocida", "unbekannte Kalibrierung", "未知的校准"),
    "bad action": _m("ação inválida", "acción no válida", "ungültige Aktion", "操作无效"),
    "bad toolhead": _m("cabeça inválida", "cabezal no válido", "ungültiger Werkzeugkopf", "工具头无效"),
    "spool #%s not found": _m("bobina #%s não encontrada", "no se encontró la bobina #%s",
                              "Spule #%s nicht gefunden", "找不到料盘 #%s"),
    "this needs the U1 Extended Firmware (with Advanced Mode on)": _m(
        "isto precisa do U1 Extended Firmware (com o Advanced Mode ligado)",
        "esto requiere el U1 Extended Firmware (con Advanced Mode activado)",
        "dafür wird die U1 Extended Firmware benötigt (mit eingeschaltetem Advanced Mode)",
        "这需要 U1 Extended Firmware（并开启 Advanced Mode）"),
    "the U1 is busy (%s); changing %s restarts Klipper or reboots the printer, which would end the print. "
    "Try again once it has finished.": _m(
        "a U1 está ocupada (%s); alterar %s reinicia o Klipper ou a impressora, o que encerraria a impressão. "
        "Tente de novo quando ela terminar.",
        "la U1 está ocupada (%s); cambiar %s reinicia Klipper o la impresora, lo que terminaría la impresión. "
        "Inténtelo de nuevo cuando haya terminado.",
        "der U1 ist beschäftigt (%s); das Ändern von %s startet Klipper oder den Drucker neu und würde den Druck "
        "beenden. Versuchen Sie es erneut, wenn er fertig ist.",
        "U1 正忙（%s）；更改 %s 会重启 Klipper 或打印机，这将终止打印。请在打印完成后重试。"),
    "the U1 is busy (%s); %s would end the print. Try again once it has finished.": _m(
        "a U1 está ocupada (%s); %s encerraria a impressão. Tente de novo quando ela terminar.",
        "la U1 está ocupada (%s); %s terminaría la impresión. Inténtelo de nuevo cuando haya terminado.",
        "der U1 ist beschäftigt (%s); %s würde den Druck beenden. Versuchen Sie es erneut, wenn er fertig ist.",
        "U1 正忙（%s）；%s 将终止打印。请在打印完成后重试。"),
    "T%d holds an RFID-tagged spool; confirm overwriting its tag data first": _m(
        "T%d tem uma bobina com etiqueta RFID; confirme antes a substituição dos dados da etiqueta",
        "T%d tiene una bobina con etiqueta RFID; confirme antes que se sobrescriban los datos de la etiqueta",
        "T%d enthält eine Spule mit RFID-Tag; bestätigen Sie zuerst das Überschreiben der Tag-Daten",
        "T%d 装有带 RFID 标签的料盘；请先确认覆盖其标签数据"),
    "… (more in the printer's console)": _m("… (mais no console da impressora)", "… (más en la consola de la impresora)",
                                            "… (mehr in der Konsole des Druckers)", "…（更多内容见打印机的控制台）"),

    # ------------------------------------------------------------ printer connection (Moonraker)
    "no printer address configured": _m("nenhum endereço de impressora configurado", "no hay dirección de impresora configurada",
                                        "keine Druckeradresse eingerichtet", "未配置打印机地址"),
    "can't read printer address %r": _m("não foi possível ler o endereço da impressora %r",
                                        "no se puede leer la dirección de la impresora %r",
                                        "die Druckeradresse %r ist nicht lesbar", "无法识别打印机地址 %r"),
    "printer response too large": _m("resposta da impressora grande demais", "respuesta de la impresora demasiado grande",
                                     "Antwort des Druckers zu groß", "打印机的应答过大"),
    "the printer sent a broken answer (%s)": _m(
        "a impressora enviou uma resposta corrompida (%s)", "la impresora envió una respuesta dañada (%s)",
        "der Drucker hat eine fehlerhafte Antwort gesendet (%s)", "打印机发来的应答已损坏（%s）"),
    "download failed (%s)": _m("o download falhou (%s)", "la descarga falló (%s)", "Herunterladen fehlgeschlagen (%s)", "下载失败（%s）"),
    "upload failed (%s)": _m("o envio falhou (%s)", "la subida falló (%s)", "Hochladen fehlgeschlagen (%s)", "上传失败（%s）"),
    "can't reach the U1 at %s": _m("não foi possível alcançar a U1 em %s", "no se puede conectar con la U1 en %s",
                                   "der U1 ist unter %s nicht erreichbar", "无法连接位于 %s 的 U1"),
    "websocket calls need plain http": _m(
        "chamadas por websocket precisam de http simples", "las llamadas por websocket necesitan http sin cifrar",
        "WebSocket-Aufrufe benötigen unverschlüsseltes http", "WebSocket 调用需要使用普通 http"),
    "printer refused the websocket": _m("a impressora recusou o websocket", "la impresora rechazó el websocket",
                                        "der Drucker hat den WebSocket abgelehnt", "打印机拒绝了 WebSocket 连接"),
    "bad websocket handshake": _m("handshake de websocket inválido", "negociación de websocket no válida",
                                  "fehlerhafter WebSocket-Handshake", "WebSocket 握手无效"),
    "websocket closed": _m("websocket fechado", "websocket cerrado", "WebSocket geschlossen", "WebSocket 已关闭"),
    "websocket message too large": _m("mensagem de websocket grande demais", "mensaje de websocket demasiado grande",
                                      "WebSocket-Nachricht zu groß", "WebSocket 消息过大"),
    "printer said: %s": _m("a impressora respondeu: %s", "la impresora respondió: %s", "Der Drucker meldet: %s", "打印机返回：%s"),
    "printer didn't answer %s": _m("a impressora não respondeu a %s", "la impresora no respondió a %s",
                                   "der Drucker hat auf %s nicht geantwortet", "打印机没有应答 %s"),
    "access denied (%s); set the API key in the printer connection settings": _m(
        "acesso negado (%s); defina a chave de API nos ajustes de conexão da impressora",
        "acceso denegado (%s); defina la clave API en los ajustes de conexión de la impresora",
        "Zugriff verweigert (%s); tragen Sie den API-Schlüssel in den Verbindungseinstellungen des Druckers ein",
        "访问被拒绝（%s）；请在打印机连接设置中填写 API 密钥"),

    # ------------------------------------------------------------ files and time-lapses
    "bad thumbnail path": _m("caminho de miniatura inválido", "ruta de miniatura no válida",
                             "ungültiger Pfad für das Vorschaubild", "缩略图路径无效"),
    "bad path %r": _m("caminho inválido %r", "ruta no válida %r", "ungültiger Pfad %r", "路径无效 %r"),
    "refusing to delete a file root": _m("uma pasta raiz não pode ser excluída", "una carpeta raíz no se puede borrar",
                                         "ein Stammordner kann nicht gelöscht werden", "不能删除根文件夹"),
    "refusing to move a file root": _m("uma pasta raiz não pode ser movida", "una carpeta raíz no se puede mover",
                                       "ein Stammordner kann nicht verschoben werden", "不能移动根文件夹"),
    "refusing to rename a file root": _m("uma pasta raiz não pode ser renomeada", "una carpeta raíz no se puede renombrar",
                                         "ein Stammordner kann nicht umbenannt werden", "不能重命名根文件夹"),
    "folder names use letters, digits, spaces, '-', '_' and '.'": _m(
        "nomes de pasta usam letras, dígitos, espaços, '-', '_' e '.'",
        "los nombres de carpeta usan letras, dígitos, espacios, '-', '_' y '.'",
        "Ordnernamen bestehen aus Buchstaben, Ziffern, Leerzeichen, '-', '_' und '.'",
        "文件夹名称只能使用字母、数字、空格、'-'、'_' 和 '.'"),
    "folders are listed from a file root": _m(
        "as pastas são listadas a partir de uma pasta raiz", "las carpetas se listan desde una carpeta raíz",
        "Ordner werden von einem Stammordner aus aufgelistet", "文件夹只能从根文件夹开始列出"),
    "files stay in their own root": _m("os arquivos ficam na própria pasta raiz", "los archivos se quedan en su propia carpeta raíz",
                                       "Dateien bleiben in ihrem eigenen Stammordner", "文件只能留在各自的根文件夹内"),
    "can't move a folder into itself": _m("uma pasta não pode ser movida para dentro dela mesma",
                                          "una carpeta no se puede mover dentro de sí misma",
                                          "ein Ordner kann nicht in sich selbst verschoben werden", "不能把文件夹移动到它自身之内"),
    "a name can't be empty, start with '.', be longer than %d characters or hold / \\ : * ? \" < > | "
    "or control characters": _m(
        "um nome não pode ser vazio, começar com '.', ter mais de %d caracteres nem conter / \\ : * ? \" < > | "
        "ou caracteres de controle",
        "un nombre no puede estar vacío, empezar por '.', tener más de %d caracteres ni contener / \\ : * ? \" < > | "
        "o caracteres de control",
        "ein Name darf nicht leer sein, nicht mit '.' beginnen, nicht länger als %d Zeichen sein und weder "
        "/ \\ : * ? \" < > | noch Steuerzeichen enthalten",
        "名称不能为空、不能以 '.' 开头、不能超过 %d 个字符，也不能包含 / \\ : * ? \" < > | 或控制字符"),
    "%s is no longer in %s; nothing was renamed": _m(
        "%s não está mais em %s; nada foi renomeado", "%s ya no está en %s; no se renombró nada",
        "%s ist nicht mehr in %s; es wurde nichts umbenannt", "%s 已不在 %s 中；未重命名任何内容"),
    "%s already has something named %s; nothing was renamed": _m(
        "%s já tem algo chamado %s; nada foi renomeado", "%s ya tiene algo llamado %s; no se renombró nada",
        "%s enthält bereits etwas mit dem Namen %s; es wurde nichts umbenannt", "%s 中已有名为 %s 的项目；未重命名任何内容"),
    "%s already has something named %s; nothing was moved": _m(
        "%s já tem algo chamado %s; nada foi movido", "%s ya tiene algo llamado %s; no se movió nada",
        "%s enthält bereits etwas mit dem Namen %s; es wurde nichts verschoben", "%s 中已有名为 %s 的项目；未移动任何内容"),
    "a print file keeps a G-code extension (.gcode, .gco or .g)": _m(
        "um arquivo de impressão mantém a extensão de G-code (.gcode, .gco ou .g)",
        "un archivo de impresión conserva una extensión de G-Code (.gcode, .gco o .g)",
        "eine Druckdatei behält eine G-Code-Endung (.gcode, .gco oder .g)",
        "打印文件必须保留 G-code 扩展名（.gcode、.gco 或 .g）"),
    "not a time-lapse picture: %r": _m("não é uma imagem de timelapse: %r", "no es una imagen de timelapse: %r",
                                       "kein Zeitraffer-Bild: %r", "不是延时摄影图片：%r"),
    "%s is not a JPEG picture": _m("%s não é uma imagem JPEG", "%s no es una imagen JPEG", "%s ist kein JPEG-Bild", "%s 不是 JPEG 图片"),
    "%s is not a time-lapse on the printer; nothing was deleted": _m(
        "%s não é um timelapse na impressora; nada foi excluído", "%s no es un timelapse de la impresora; no se borró nada",
        "%s ist kein Zeitraffer auf dem Drucker; es wurde nichts gelöscht", "%s 不是打印机上的延时摄影；未删除任何内容"),
    "download interrupted, partial file kept at %s (%s)": _m(
        "download interrompido, arquivo parcial mantido em %s (%s)",
        "descarga interrumpida, archivo parcial conservado en %s (%s)",
        "Herunterladen unterbrochen, die unvollständige Datei liegt unter %s (%s)",
        "下载中断，未完成的文件保留在 %s（%s）"),
    "download kept at %s: couldn't give it its final name (%s)": _m(
        "download mantido em %s: não foi possível dar o nome final (%s)",
        "descarga conservada en %s: no se le pudo dar su nombre final (%s)",
        "Download liegt unter %s: Der endgültige Name konnte nicht vergeben werden (%s)",
        "下载的文件保留在 %s：无法改为最终名称（%s）"),
    "too many files named %s in %s": _m("há arquivos demais chamados %s em %s", "hay demasiados archivos llamados %s en %s",
                                        "zu viele Dateien mit dem Namen %s in %s", "名为 %s 的文件过多（位于 %s）"),

    # ------------------------------------------------------------ Spoolman and Spooler's stock
    "Spoolman not configured: set its URL in u1control settings": _m(
        "Spoolman não configurado: defina a URL nos ajustes do u1control",
        "Spoolman no está configurado: defina su URL en los ajustes de u1control",
        "Spoolman ist nicht eingerichtet: Tragen Sie die URL in den Einstellungen von u1control ein",
        "未配置 Spoolman：请在 u1control 的设置中填写其 URL"),
    "Spoolman said HTTP %d": _m("o Spoolman respondeu HTTP %d", "Spoolman respondió HTTP %d",
                                "Spoolman meldet HTTP %d", "Spoolman 返回 HTTP %d"),
    "can't reach Spoolman at %s (%s)": _m(
        "não foi possível alcançar o Spoolman em %s (%s)", "no se puede conectar con Spoolman en %s (%s)",
        "Spoolman ist unter %s nicht erreichbar (%s)", "无法连接位于 %s 的 Spoolman（%s）"),
    "%s didn't answer like Spoolman (%s)": _m(
        "%s não respondeu como o Spoolman (%s)", "%s no respondió como Spoolman (%s)",
        "%s hat nicht wie Spoolman geantwortet (%s)", "%s 的应答不像 Spoolman（%s）"),
    "Spooler's stock list changed since this one was shown; nothing was written. Pick the spool again.": _m(
        "A lista de estoque do Spooler mudou desde que esta foi mostrada; nada foi gravado. Escolha a bobina de novo.",
        "La lista de inventario de Spooler cambió desde que se mostró esta; no se escribió nada. Elija la bobina de nuevo.",
        "Die Bestandsliste von Spooler hat sich geändert, seit diese angezeigt wurde; es wurde nichts geschrieben. "
        "Wählen Sie die Spule erneut.",
        "此列表显示之后 Spooler 的库存列表已更改；未写入任何内容。请重新选择料盘。"),
    "no spool chosen": _m("nenhuma bobina escolhida", "no se eligió ninguna bobina", "keine Spule gewählt", "未选择料盘"),
    "Spool #%d is no longer in Spooler's stock list; nothing was written.": _m(
        "A bobina #%d não está mais na lista de estoque do Spooler; nada foi gravado.",
        "La bobina #%d ya no está en la lista de inventario de Spooler; no se escribió nada.",
        "Spule #%d steht nicht mehr in der Bestandsliste von Spooler; es wurde nichts geschrieben.",
        "料盘 #%d 已不在 Spooler 的库存列表中；未写入任何内容。"),
    "U1 Control's Spoolman (%s) isn't the one Spooler uses (%s); nothing was written. "
    "Set the same Spoolman address in both.": _m(
        "O Spoolman do U1 Control (%s) não é o que o Spooler usa (%s); nada foi gravado. "
        "Defina o mesmo endereço do Spoolman nos dois.",
        "El Spoolman de U1 Control (%s) no es el que usa Spooler (%s); no se escribió nada. "
        "Defina la misma dirección de Spoolman en ambos.",
        "Das Spoolman von U1 Control (%s) ist nicht das von Spooler (%s); es wurde nichts geschrieben. "
        "Tragen Sie in beiden dieselbe Spoolman-Adresse ein.",
        "U1 Control 使用的 Spoolman（%s）与 Spooler 使用的（%s）不同；未写入任何内容。请在两者中设置相同的 Spoolman 地址。"),
    "Spool #%d isn't in the Spoolman U1 Control reaches; nothing was written. "
    "Do both plugins use the same Spoolman?": _m(
        "A bobina #%d não está no Spoolman que o U1 Control alcança; nada foi gravado. "
        "Os dois plugins usam o mesmo Spoolman?",
        "La bobina #%d no está en el Spoolman al que llega U1 Control; no se escribió nada. "
        "¿Usan ambos plugins el mismo Spoolman?",
        "Spule #%d ist nicht in dem Spoolman, das U1 Control erreicht; es wurde nichts geschrieben. "
        "Verwenden beide Plugins dasselbe Spoolman?",
        "U1 Control 连接的 Spoolman 中没有料盘 #%d；未写入任何内容。两个插件使用的是同一个 Spoolman 吗？"),
    "Spool #%d holds another filament in the Spoolman U1 Control reaches than in Spooler's list; nothing was "
    "written. Do both plugins use the same Spoolman?": _m(
        "A bobina #%d tem outro filamento no Spoolman que o U1 Control alcança do que na lista do Spooler; nada foi "
        "gravado. Os dois plugins usam o mesmo Spoolman?",
        "La bobina #%d tiene otro filamento en el Spoolman al que llega U1 Control que en la lista de Spooler; no se "
        "escribió nada. ¿Usan ambos plugins el mismo Spoolman?",
        "Spule #%d hat in dem Spoolman, das U1 Control erreicht, ein anderes Filament als in der Liste von Spooler; "
        "es wurde nichts geschrieben. Verwenden beide Plugins dasselbe Spoolman?",
        "料盘 #%d 在 U1 Control 连接的 Spoolman 中的耗材丝与 Spooler 列表中的不同；未写入任何内容。"
        "两个插件使用的是同一个 Spoolman 吗？"),
    "Spooler is running in this OrcaSlicer.": _m(
        "O Spooler está em execução neste OrcaSlicer.", "Spooler se está ejecutando en este OrcaSlicer.",
        "Spooler läuft in diesem OrcaSlicer.", "Spooler 正在此 OrcaSlicer 中运行。"),
    "Spooler isn't running in this OrcaSlicer.": _m(
        "O Spooler não está em execução neste OrcaSlicer.", "Spooler no se está ejecutando en este OrcaSlicer.",
        "Spooler läuft nicht in diesem OrcaSlicer.", "Spooler 未在此 OrcaSlicer 中运行。"),
    "Spooler was unloaded or disabled.": _m(
        "O Spooler foi descarregado ou desativado.", "Spooler se descargó o se desactivó.",
        "Spooler wurde entladen oder deaktiviert.", "Spooler 已被卸载或禁用。"),
    "Spooler stopped answering.": _m("O Spooler parou de responder.", "Spooler dejó de responder.",
                                     "Spooler antwortet nicht mehr.", "Spooler 已停止应答。"),
    "Spooler is running in another OrcaSlicer window, not this one.": _m(
        "O Spooler está em execução em outra janela do OrcaSlicer, não nesta.",
        "Spooler se está ejecutando en otra ventana de OrcaSlicer, no en esta.",
        "Spooler läuft in einem anderen OrcaSlicer-Fenster, nicht in diesem.",
        "Spooler 正在另一个 OrcaSlicer 窗口中运行，而不是此窗口。"),
    "This Spooler version can't share its stock with U1 Control.": _m(
        "Esta versão do Spooler não consegue compartilhar o estoque com o U1 Control.",
        "Esta versión de Spooler no puede compartir su inventario con U1 Control.",
        "Diese Spooler-Version kann ihren Bestand nicht mit U1 Control teilen.",
        "此版本的 Spooler 无法与 U1 Control 共享库存。"),
    "not a presence file": _m("não é um arquivo de presença", "no es un archivo de presencia",
                              "keine Präsenzdatei", "不是在线状态文件"),
    "presence version %r": _m("versão de presença %r", "versión de presencia %r", "Präsenzversion %r", "在线状态版本 %r"),
    "presence without ts or session": _m("presença sem ts ou sessão", "presencia sin ts ni sesión",
                                         "Präsenz ohne ts oder Sitzung", "在线状态缺少 ts 或会话"),
    "last seen %d s ago": _m("visto pela última vez há %d s", "visto por última vez hace %d s",
                             "zuletzt vor %d s gesehen", "上次出现在 %d 秒前"),
    "stock list version %r": _m("versão da lista de estoque %r", "versión de la lista de inventario %r",
                                "Version der Bestandsliste %r", "库存列表版本 %r"),

    # ------------------------------------------------------------ Extended Firmware settings
    "Firmware Config API not available": _m(
        "API do Firmware Config indisponível", "la API de Firmware Config no está disponible",
        "Firmware-Config-API nicht verfügbar", "Firmware Config API 不可用"),
    "invalid setting %r=%r": _m("ajuste inválido %r=%r", "ajuste no válido %r=%r", "ungültige Einstellung %r=%r", "设置无效 %r=%r"),
    "invalid inputs for %s": _m("entradas inválidas para %s", "entradas no válidas para %s",
                                "ungültige Eingaben für %s", "%s 的输入无效"),
    "unsupported action %r": _m("ação não suportada %r", "acción no compatible %r", "nicht unterstützte Aktion %r", "不支持的操作 %r"),
    "the printer didn't report how this ended; reload the settings to see what applied": _m(
        "a impressora não informou como isto terminou; recarregue os ajustes para ver o que foi aplicado",
        "la impresora no informó de cómo terminó esto; recargue los ajustes para ver qué se aplicó",
        "der Drucker hat nicht gemeldet, wie dies ausging; laden Sie die Einstellungen neu, um zu sehen, was gilt",
        "打印机没有报告此操作的结果；请重新加载设置查看已生效的内容"),
    "Apply this change?": _m("Aplicar esta alteração?", "¿Aplicar este cambio?", "Diese Änderung anwenden?", "应用此更改？"),
    "Firmware Config sent settings u1control can't read (%s)": _m(
        "o Firmware Config enviou ajustes que o u1control não consegue ler (%s)",
        "Firmware Config envió ajustes que u1control no puede leer (%s)",
        "Firmware Config hat Einstellungen gesendet, die u1control nicht lesen kann (%s)",
        "Firmware Config 发来的设置 u1control 无法读取（%s）"),

    # ------------------------------------------------------------ filament use (Spoolman ledger)
    "unreadable (%s)": _m("ilegível (%s)", "ilegible (%s)", "unlesbar (%s)", "无法读取（%s）"),
    "of an unknown format": _m("de um formato desconhecido", "de un formato desconocido",
                               "in einem unbekannten Format", "格式未知"),
    "%d unreadable job(s) in %s were skipped": _m(
        "%d impressão(ões) ilegível(is) em %s foi(ram) ignorada(s)", "se omitieron %d trabajo(s) ilegible(s) en %s",
        "%d unlesbare(r) Auftrag/Aufträge in %s wurde(n) übersprungen", "已跳过 %d 个无法读取的任务（位于 %s）"),
    "%d unreadable unconfirmed entry in %s were skipped; check Spoolman for prints that finished meanwhile": _m(
        "%d lançamento não confirmado ilegível em %s foi ignorado; confira no Spoolman as impressões que terminaram "
        "nesse meio-tempo",
        "se omitió %d entrada sin confirmar ilegible en %s; compruebe en Spoolman las impresiones que terminaron "
        "mientras tanto",
        "%d unlesbarer unbestätigter Eintrag in %s wurde übersprungen; prüfen Sie in Spoolman die Drucke, die "
        "inzwischen fertig wurden",
        "已跳过 %d 条无法读取的未确认记录（位于 %s）；请在 Spoolman 中检查此期间完成的打印"),
    "%d unreadable unconfirmed entries in %s were skipped; check Spoolman for prints that finished meanwhile": _m(
        "%d lançamentos não confirmados ilegíveis em %s foram ignorados; confira no Spoolman as impressões que "
        "terminaram nesse meio-tempo",
        "se omitieron %d entradas sin confirmar ilegibles en %s; compruebe en Spoolman las impresiones que "
        "terminaron mientras tanto",
        "%d unlesbare unbestätigte Einträge in %s wurden übersprungen; prüfen Sie in Spoolman die Drucke, die "
        "inzwischen fertig wurden",
        "已跳过 %d 条无法读取的未确认记录（位于 %s）；请在 Spoolman 中检查此期间完成的打印"),
    "the print ledger %s is %s and could not be moved aside (%s); it was not used": _m(
        "o registro de impressões %s é %s e não pôde ser posto de lado (%s); não foi usado",
        "el registro de impresiones %s es %s y no se pudo apartar (%s); no se usó",
        "das Druckprotokoll %s ist %s und konnte nicht beiseitegelegt werden (%s); es wurde nicht verwendet",
        "打印记录 %s %s，且无法移走（%s）；未使用该文件"),
    "the print ledger was %s; it was kept as %s and not used. Check Spoolman for prints that finished meanwhile.": _m(
        "o registro de impressões era %s; foi guardado como %s e não foi usado. Confira no Spoolman as impressões "
        "que terminaram nesse meio-tempo.",
        "el registro de impresiones era %s; se conservó como %s y no se usó. Compruebe en Spoolman las impresiones "
        "que terminaron mientras tanto.",
        "das Druckprotokoll war %s; es wurde als %s aufbewahrt und nicht verwendet. Prüfen Sie in Spoolman die "
        "Drucke, die inzwischen fertig wurden.",
        "打印记录%s；已另存为 %s，未使用。请在 Spoolman 中检查此期间完成的打印。"),
    "OrcaSlicer closed while this was being recorded": _m(
        "o OrcaSlicer fechou enquanto isto era lançado", "OrcaSlicer se cerró mientras esto se registraba",
        "OrcaSlicer wurde geschlossen, während dies eingetragen wurde", "记录此项时 OrcaSlicer 已关闭"),
    "can't save the print ledger (%s); pending prints won't survive a restart": _m(
        "não consegue salvar o registro de impressões (%s); as impressões pendentes não sobrevivem a um reinício",
        "no se puede guardar el registro de impresiones (%s); las impresiones pendientes no sobrevivirán a un reinicio",
        "das Druckprotokoll kann nicht gespeichert werden (%s); ausstehende Drucke überstehen keinen Neustart",
        "无法保存打印记录（%s）；待处理的打印在重启后会丢失"),
    "That unconfirmed entry is no longer listed; nothing was changed.": _m(
        "Esse lançamento não confirmado não está mais na lista; nada foi alterado.",
        "Esa entrada sin confirmar ya no está en la lista; no se cambió nada.",
        "Dieser unbestätigte Eintrag steht nicht mehr in der Liste; es wurde nichts geändert.",
        "该未确认记录已不在列表中；未做任何更改。"),
    "U1 Control %s.": _m("O U1 Control %s.", "U1 Control %s.", "U1 Control %s.", "U1 Control %s。"),
    "Spoolman usage for %s not recorded: %s": _m(
        "Consumo de %s não lançado no Spoolman: %s", "Uso de %s no registrado en Spoolman: %s",
        "Verbrauch für %s nicht in Spoolman eingetragen: %s", "%s 的用量未记入 Spoolman：%s"),
    "printing before OrcaSlicer closed; how it ended wasn't seen": _m(
        "estava imprimindo antes de o OrcaSlicer fechar; não se viu como terminou",
        "se estaba imprimiendo antes de cerrarse OrcaSlicer; no se vio cómo terminó",
        "wurde noch gedruckt, als OrcaSlicer geschlossen wurde; das Ende wurde nicht beobachtet",
        "OrcaSlicer 关闭前正在打印；未看到其结果"),
    "finished without being seen printing": _m(
        "terminou sem ter sido vista imprimindo", "terminó sin que se la viera imprimiendo",
        "wurde fertig, ohne beim Drucken beobachtet worden zu sein", "已完成，但未曾看到它在打印"),
    "%s was printing before OrcaSlicer closed and u1control didn't see how it ended, so its filament use was not "
    "recorded. Check Spoolman.": _m(
        "%s estava imprimindo antes de o OrcaSlicer fechar e o u1control não viu como terminou, então o consumo de "
        "filamento não foi lançado. Confira o Spoolman.",
        "%s se estaba imprimiendo antes de cerrarse OrcaSlicer y u1control no vio cómo terminó, así que su uso de "
        "filamento no se registró. Compruebe Spoolman.",
        "%s wurde noch gedruckt, als OrcaSlicer geschlossen wurde, und u1control hat das Ende nicht beobachtet; der "
        "Filamentverbrauch wurde daher nicht eingetragen. Prüfen Sie Spoolman.",
        "OrcaSlicer 关闭前 %s 正在打印，u1control 未看到其结果，因此未记录它的耗材丝用量。请检查 Spoolman。"),
    "%s finished, but u1control never saw it printing, so its filament use was not recorded. Check Spoolman.": _m(
        "%s terminou, mas o u1control nunca a viu imprimindo, então o consumo de filamento não foi lançado. "
        "Confira o Spoolman.",
        "%s terminó, pero u1control nunca la vio imprimiéndose, así que su uso de filamento no se registró. "
        "Compruebe Spoolman.",
        "%s wurde fertig, aber u1control hat den Druck nie beobachtet; der Filamentverbrauch wurde daher nicht "
        "eingetragen. Prüfen Sie Spoolman.",
        "%s 已完成，但 u1control 从未看到它在打印，因此未记录它的耗材丝用量。请检查 Spoolman。"),
    "%s was cancelled or failed; its filament use was not recorded.": _m(
        "%s foi cancelada ou falhou; o consumo de filamento não foi lançado.",
        "%s se canceló o falló; su uso de filamento no se registró.",
        "%s wurde abgebrochen oder ist fehlgeschlagen; der Filamentverbrauch wurde nicht eingetragen.",
        "%s 已取消或失败；未记录它的耗材丝用量。"),
    "u1control stopped waiting for %s to finish; its filament use was not recorded.": _m(
        "o u1control parou de esperar %s terminar; o consumo de filamento não foi lançado.",
        "u1control dejó de esperar a que %s terminara; su uso de filamento no se registró.",
        "u1control wartet nicht länger auf das Ende von %s; der Filamentverbrauch wurde nicht eingetragen.",
        "u1control 已停止等待 %s 完成；未记录它的耗材丝用量。"),
    "Spoolman usage for %s waits for a retry: %s": _m(
        "O lançamento de %s no Spoolman aguarda nova tentativa: %s",
        "El registro de %s en Spoolman espera un reintento: %s",
        "Der Spoolman-Eintrag für %s wartet auf einen neuen Versuch: %s", "%s 的 Spoolman 用量等待重试：%s"),
    "Spoolman usage for %s waits: %s.": _m(
        "O lançamento de %s no Spoolman aguarda: %s.", "El registro de %s en Spoolman espera: %s.",
        "Der Spoolman-Eintrag für %s wartet: %s.", "%s 的 Spoolman 用量正在等待：%s。"),
    "Spoolman may not have recorded %s g on spool #%d (T%d): %s. Check spool #%d before adding it by hand; "
    "u1control won't repeat it.": _m(
        "O Spoolman pode não ter lançado %s g na bobina #%d (T%d): %s. Confira a bobina #%d antes de lançar à mão; "
        "o u1control não vai repetir.",
        "Puede que Spoolman no haya registrado %s g en la bobina #%d (T%d): %s. Compruebe la bobina #%d antes de "
        "añadirlo a mano; u1control no lo repetirá.",
        "Spoolman hat %s g auf Spule #%d (T%d) möglicherweise nicht eingetragen: %s. Prüfen Sie Spule #%d, bevor "
        "Sie es von Hand nachtragen; u1control wiederholt es nicht.",
        "Spoolman 可能没有记录这 %s g（料盘 #%d，T%d）：%s。手动补记前请先检查料盘 #%d；u1control 不会重复记录。"),
    "Spoolman updated with this print's filament use": _m(
        "Spoolman atualizado com o consumo de filamento desta impressão",
        "Spoolman actualizado con el uso de filamento de esta impresión",
        "Der Filamentverbrauch dieses Drucks wurde in Spoolman eingetragen", "已把本次打印的耗材丝用量更新到 Spoolman"),
    "No Spoolman spool was linked to %s; that filament use was not recorded.": _m(
        "Nenhuma bobina do Spoolman estava vinculada a %s; esse consumo de filamento não foi lançado.",
        "No había ninguna bobina de Spoolman asignada a %s; ese uso de filamento no se registró.",
        "%s war keine Spoolman-Spule zugewiesen; dieser Filamentverbrauch wurde nicht eingetragen.",
        "%s 未绑定 Spoolman 料盘；未记录这部分耗材丝用量。"),
    "can't tell yet whether the printer runs the Extended Firmware": _m(
        "ainda não dá para saber se a impressora usa o Extended Firmware",
        "aún no se puede saber si la impresora usa el Extended Firmware",
        "noch ist unklar, ob auf dem Drucker die Extended Firmware läuft", "尚无法判断打印机是否运行 Extended Firmware"),
}
