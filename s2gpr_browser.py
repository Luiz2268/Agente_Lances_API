import re
from urllib.parse import urlsplit
from playwright.async_api import async_playwright

S2GPR_LOGIN_URL = (
    "https://s2gpr.sefaz.ce.gov.br/"
    "cotacao-web/padrao-web/paginas/seguranca/login.seam"
)

S2GPR_QUOTATIONS_URL = (
    "https://s2gpr.sefaz.ce.gov.br/"
    "cotacao-web/paginas/proposta/PropostaList.seam"
)


class S2GPRBrowser:
    def __init__(self):
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self.connected = False
        self.status = "disconnected"
        self.last_error_code = None

    async def start(self):
        if self.browser:
            return
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        self.context = await self.browser.new_context(
            viewport={"width": 1440, "height": 900},
            ignore_https_errors=True,
        )
        self.page = await self.context.new_page()

    async def _safe_body_text(self):
        try:
            return (await self.page.inner_text("body")).lower()
        except Exception:
            return ""

    async def _login_form_visible(self):
        try:
            passwords = self.page.locator('input[type="password"]')
            return await passwords.count() > 0 and await passwords.first.is_visible()
        except Exception:
            return False

    async def connect(self, usuario: str, senha: str):
        await self.start()
        self.connected = False
        self.status = "connecting"
        self.last_error_code = None

        try:
            await self.page.goto(
                S2GPR_LOGIN_URL,
                wait_until="domcontentloaded",
                timeout=60000,
            )

            body = await self._safe_body_text()
            if "captcha" in body or "recaptcha" in body:
                self.status = "human_action_required"
                self.last_error_code = "captcha"
                return {"connected": False, "status": self.status, "reason": self.last_error_code}

            usuario_input = self.page.locator(
                'input[type="text"], input[name*="usuario" i], input[id*="usuario" i], '
                'input[name*="login" i], input[id*="login" i], '
                'input[name*="cpf" i], input[id*="cpf" i]'
            ).first
            senha_input = self.page.locator('input[type="password"]').first

            await usuario_input.wait_for(state="visible", timeout=15000)
            await senha_input.wait_for(state="visible", timeout=15000)
            await usuario_input.fill(usuario)
            await senha_input.fill(senha)

            login_selectors = [
                'input[type="submit"]',
                'input[type="button"][value*="entrar" i]',
                'input[value*="entrar" i]',
                'button[type="submit"]',
                'button:has-text("Entrar")',
                'a:has-text("Entrar")',
                'text=/^Entrar$/i',
            ]
            clicked = False
            for selector in login_selectors:
                locator = self.page.locator(selector).first
                try:
                    if await locator.count() > 0 and await locator.is_visible():
                        await locator.click(timeout=5000)
                        clicked = True
                        break
                except Exception:
                    continue
            if not clicked:
                await senha_input.press("Enter")

            try:
                await self.page.wait_for_load_state("domcontentloaded", timeout=20000)
            except Exception:
                pass
            await self.page.wait_for_timeout(2500)

            current_url = self.page.url
            body = await self._safe_body_text()

            if any(x in body for x in [
                "captcha", "recaptcha", "autenticação em dois fatores",
                "autenticacao em dois fatores", "código de verificação",
                "codigo de verificacao",
            ]):
                self.status = "human_action_required"
                self.last_error_code = "captcha_or_mfa"
                return {"connected": False, "status": self.status, "reason": self.last_error_code}

            if await self._login_form_visible():
                self.status = "authentication_failed"
                self.last_error_code = "login_form_still_visible"
                return {
                    "connected": False,
                    "status": self.status,
                    "reason": self.last_error_code,
                    "url": current_url,
                }

            self.connected = True
            self.status = "authenticated"
            return {"connected": True, "status": self.status, "url": current_url}

        except Exception as exc:
            self.connected = False
            self.status = "error"
            name = type(exc).__name__.lower()
            message = str(exc).lower()
            if "timeout" in name or "timeout" in message:
                self.last_error_code = "portal_timeout"
            elif "net::" in message:
                self.last_error_code = "portal_network_error"
            else:
                self.last_error_code = "connector_error"
            return {
                "connected": False,
                "status": self.status,
                "reason": self.last_error_code,
            }

    async def session_status(self):
        return {
            "connected": self.connected,
            "status": self.status,
            "reason": self.last_error_code,
            "url": self.page.url if self.page else None,
        }

    @staticmethod
    def _safe_nav_value(value):
        """Return only non-sensitive navigation metadata."""
        if not value:
            return None
        value = " ".join(str(value).split())[:160]
        low = value.lower()
        if any(secret in low for secret in (
            "senha", "password", "token", "authorization", "cpf", "usuário:", "usuario:"
        )):
            return None
        if re.search(r"\\b\\d{3}\\.?\\d{3}\\.?\\d{3}-?\\d{2}\\b", value):
            return None
        return value or None

    @staticmethod
    def _safe_url_path(value):
        if not value:
            return None
        try:
            if str(value).lower().startswith("javascript:"):
                return None
            parsed = urlsplit(str(value))
            return parsed.path or None
        except Exception:
            return None

    async def navigation_diagnostic(self):
        """Safe, read-only snapshot of menu/navigation controls; never returns page HTML."""
        if not self.connected or not self.page:
            return {"ok": False, "status": "not_authenticated", "frames": []}

        keywords = (
            "cota", "consulta", "pesquis", "aquisi", "fornecedor",
            "negocia", "proposta", "process", "menu", "coep"
        )
        frames_out = []

        for frame in self.page.frames:
            controls = []
            try:
                locator = frame.locator(
                    'a, button, input[type="button"], input[type="submit"]'
                )
                total = min(await locator.count(), 250)
                for i in range(total):
                    item = locator.nth(i)
                    try:
                        label = " ".join(filter(None, [
                            (await item.inner_text()).strip(),
                            (await item.get_attribute("value") or "").strip(),
                            (await item.get_attribute("title") or "").strip(),
                            (await item.get_attribute("aria-label") or "").strip(),
                        ]))
                        safe_label = self._safe_nav_value(label)
                        href = await item.get_attribute("href")
                        element_id = self._safe_nav_value(await item.get_attribute("id"))
                        element_name = self._safe_nav_value(await item.get_attribute("name"))
                        onclick = await item.get_attribute("onclick")
                        haystack = " ".join(filter(None, [
                            safe_label, element_id, element_name,
                            self._safe_url_path(href),
                        ])).lower()
                        if not any(word in haystack for word in keywords):
                            continue
                        tag = await item.evaluate("(e) => e.tagName.toLowerCase()")
                        controls.append({
                            "tag": tag,
                            "text": safe_label,
                            "id": element_id,
                            "name": element_name,
                            "href_path": self._safe_url_path(href),
                            "has_onclick": bool(onclick),
                        })
                    except Exception:
                        continue
            except Exception:
                pass

            frames_out.append({
                "url_path": self._safe_url_path(frame.url),
                "controls": controls[:80],
            })

        return {
            "ok": True,
            "status": self.status,
            "page_path": self._safe_url_path(self.page.url),
            "frame_count": len(frames_out),
            "frames": frames_out,
        }

    async def _open_quotations_search(self):
        """Open the authenticated quotation search page in read-only mode."""
        markers = (
            "objeto da cotação",
            "objeto da cotacao",
            "só cotações que participo",
            "so cotacoes que participo",
            "nº coep",
            "n° coep",
        )

        body = await self._safe_body_text()
        if any(marker in body for marker in markers):
            return True

        # The authenticated S2GPR session can open the official quotation
        # search route directly. This avoids depending on JSF menu rendering.
        try:
            await self.page.goto(
                S2GPR_QUOTATIONS_URL,
                wait_until="domcontentloaded",
                timeout=60000,
            )
            await self.page.wait_for_timeout(1800)

            if await self._login_form_visible():
                self.connected = False
                self.status = "session_expired"
                self.last_error_code = "session_expired_on_quotations"
                return False

            body = await self._safe_body_text()
            if any(marker in body for marker in markers):
                return True
        except Exception:
            pass

        # Fallback for portal changes: inspect rendered controls and JSF actions.
        candidates = self.page.locator(
            'a, button, input[type="button"], input[type="submit"]'
        )
        for i in range(await candidates.count()):
            item = candidates.nth(i)
            try:
                label = " ".join(filter(None, [
                    (await item.inner_text()).strip(),
                    (await item.get_attribute("value") or "").strip(),
                    (await item.get_attribute("title") or "").strip(),
                ])).lower()
                href = (await item.get_attribute("href") or "").lower()
                onclick = (await item.get_attribute("onclick") or "").lower()
                haystack = f"{label} {href} {onclick}"

                if not any(word in haystack for word in ("cotaç", "cotac", "coep")):
                    continue
                if any(word in haystack for word in ("lance", "excluir proposta", "participar")):
                    continue

                await item.click(timeout=5000)
                try:
                    await self.page.wait_for_load_state(
                        "domcontentloaded", timeout=12000
                    )
                except Exception:
                    pass
                await self.page.wait_for_timeout(1200)

                body = await self._safe_body_text()
                if any(marker in body for marker in markers):
                    return True
            except Exception:
                continue

        return False

    async def quotations(self, mine: bool = True, status: str | None = None):
        """Read-only extraction of the authenticated S2GPR quotations table."""
        if not self.connected or not self.page:
            return {"ok": False, "status": "not_authenticated", "items": []}

        if await self._login_form_visible():
            self.connected = False
            self.status = "session_expired"
            return {"ok": False, "status": self.status, "items": []}

        if not await self._open_quotations_search():
            diagnostic = await self.navigation_diagnostic()
            return {
                "ok": False,
                "status": "quotations_page_not_found",
                "url": self.page.url,
                "items": [],
                "diagnostic": diagnostic,
            }

        # Optional filters. Search controls only; never proposal/action controls.
        if mine:
            try:
                labels = self.page.locator("label")
                for i in range(await labels.count()):
                    label = labels.nth(i)
                    label_text = (await label.inner_text()).lower()
                    if "cotações que participo" in label_text or "cotacoes que participo" in label_text:
                        target = await label.get_attribute("for")
                        checkbox = self.page.locator(f'[id="{target}"]') if target else label.locator('input[type="checkbox"]')
                        if await checkbox.count() and not await checkbox.first.is_checked():
                            await checkbox.first.check()
                        break
                else:
                    checkboxes = self.page.locator('input[type="checkbox"]')
                    for i in range(await checkboxes.count()):
                        cb = checkboxes.nth(i)
                        meta = " ".join(filter(None, [
                            await cb.get_attribute("id"),
                            await cb.get_attribute("name"),
                            await cb.get_attribute("title"),
                        ])).lower()
                        if "particip" in meta and not await cb.is_checked():
                            await cb.check()
                            break
            except Exception:
                pass

        if status:
            try:
                selects = self.page.locator("select")
                wanted = status.replace("_", " ").lower()
                for i in range(await selects.count()):
                    select = selects.nth(i)
                    options = select.locator("option")
                    for j in range(await options.count()):
                        opt = options.nth(j)
                        txt = (await opt.inner_text()).strip()
                        if wanted in txt.lower():
                            value = await opt.get_attribute("value")
                            if value is not None:
                                await select.select_option(value=value)
                            raise StopAsyncIteration
            except StopAsyncIteration:
                pass
            except Exception:
                pass

        # Execute only the search action.
        try:
            search = self.page.locator(
                'input[value="Pesquisar"], input[value*="Pesquisar"], '
                'button:has-text("Pesquisar"), a:has-text("Pesquisar")'
            ).first
            if await search.count() and await search.is_visible():
                await search.click(timeout=5000)
                try:
                    await self.page.wait_for_load_state("domcontentloaded", timeout=12000)
                except Exception:
                    pass
                await self.page.wait_for_timeout(1500)
        except Exception:
            pass

        tables = self.page.locator("table")
        result_table = None
        for i in range(await tables.count()):
            table = tables.nth(i)
            try:
                table_text = (await table.inner_text()).lower()
                if "coep" in table_text and ("objeto da cotação" in table_text or "objeto da cotacao" in table_text):
                    result_table = table
                    break
            except Exception:
                continue

        if result_table is None:
            return {
                "ok": False,
                "status": "quotations_table_not_found",
                "url": self.page.url,
                "items": [],
            }

        rows = result_table.locator("tr")
        items = []
        for i in range(await rows.count()):
            cells = rows.nth(i).locator("td")
            count = await cells.count()
            if count < 6:
                continue
            values = [" ".join((await cells.nth(j).inner_text()).split()) for j in range(count)]
            coep_index = next(
                (j for j, value in enumerate(values)
                 if "/" in value and any(ch.isdigit() for ch in value)),
                None,
            )
            if coep_index is None:
                continue

            def val(offset):
                idx = coep_index + offset
                return values[idx] if idx < len(values) else None

            items.append({
                "coep": val(0),
                "alert": val(1),
                "status": val(2),
                "viproc": val(3),
                "object": val(4),
                "term_promoter_delivery": val(5),
                "acquisition_type": val(6),
                "reception_opening": val(7),
            })

        return {
            "ok": True,
            "status": "authenticated",
            "mine": mine,
            "filter_status": status,
            "url": self.page.url,
            "count": len(items),
            "items": items[:200],
        }

    async def disconnect(self):
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
        self.playwright = self.browser = self.context = self.page = None
        self.connected = False
        self.status = "disconnected"
        self.last_error_code = None
        return {"connected": False, "status": self.status}


s2gpr_browser = S2GPRBrowser()
