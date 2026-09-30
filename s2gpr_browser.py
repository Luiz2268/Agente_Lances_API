from playwright.async_api import async_playwright

S2GPR_LOGIN_URL = (
    "https://s2gpr.sefaz.ce.gov.br/"
    "cotacao-web/padrao-web/paginas/seguranca/login.seam"
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

    async def quotations(self, mine: bool = True, status: str | None = None):
        """Read-only extraction of the authenticated S2GPR quotations table."""
        if not self.connected or not self.page:
            return {"ok": False, "status": "not_authenticated", "items": []}

        if await self._login_form_visible():
            self.connected = False
            self.status = "session_expired"
            return {"ok": False, "status": self.status, "items": []}

        # Locate the quotations/search page from the authenticated session.
        body = await self._safe_body_text()
        if not ("nº coep" in body or "n° coep" in body or "objeto da cotação" in body):
            candidates = self.page.locator("a")
            for i in range(await candidates.count()):
                link = candidates.nth(i)
                try:
                    label = " ".join((await link.inner_text()).split()).lower()
                    if "cotaç" in label or "cotac" in label:
                        await link.click(timeout=5000)
                        try:
                            await self.page.wait_for_load_state("domcontentloaded", timeout=15000)
                        except Exception:
                            pass
                        await self.page.wait_for_timeout(1200)
                        body = await self._safe_body_text()
                        if "objeto da cotação" in body or "coep" in body:
                            break
                except Exception:
                    continue

        # Optional filters. We only interact with search controls; never proposal/action controls.
        if mine:
            try:
                labels = self.page.locator("label")
                for i in range(await labels.count()):
                    label = labels.nth(i)
                    text = (await label.inner_text()).lower()
                    if "só cotações que participo" in text or "so cotacoes que participo" in text:
                        target = await label.get_attribute("for")
                        checkbox = self.page.locator(f'#{target}') if target else label.locator('input[type="checkbox"]')
                        if await checkbox.count() and not await checkbox.first.is_checked():
                            await checkbox.first.check()
                        break
            except Exception:
                pass

        if status:
            try:
                selects = self.page.locator("select")
                for i in range(await selects.count()):
                    select = selects.nth(i)
                    options = [x.lower() for x in await select.locator("option").all_inner_texts()]
                    if any("recebendo propostas" in x for x in options):
                        wanted = status.replace("_", " ").lower()
                        for opt in await select.locator("option").all():
                            txt = (await opt.inner_text()).strip()
                            if wanted in txt.lower():
                                value = await opt.get_attribute("value")
                                if value is not None:
                                    await select.select_option(value=value)
                                break
                        break
            except Exception:
                pass

        # Execute only the search action if present.
        try:
            search = self.page.get_by_text("Pesquisar", exact=True).first
            if await search.count() and await search.is_visible():
                await search.click(timeout=5000)
                await self.page.wait_for_timeout(1500)
        except Exception:
            pass

        # Find the result table by its known S2GPR headers.
        tables = self.page.locator("table")
        result_table = None
        for i in range(await tables.count()):
            table = tables.nth(i)
            try:
                text = (await table.inner_text()).lower()
                if "coep" in text and ("objeto da cotação" in text or "objeto da cotacao" in text):
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
            row = rows.nth(i)
            cells = row.locator("td")
            count = await cells.count()
            if count < 6:
                continue
            values = [" ".join((await cells.nth(j).inner_text()).split()) for j in range(count)]
            # S2GPR currently includes selection/action cells before the business columns.
            coep_index = next((j for j, v in enumerate(values) if "/" in v and any(ch.isdigit() for ch in v)), None)
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
