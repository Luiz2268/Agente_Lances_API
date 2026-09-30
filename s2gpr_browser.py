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

    async def quotations(self):
        """Read-only discovery of quotation links/items from an authenticated S2GPR page."""
        if not self.connected or not self.page:
            return {"ok": False, "status": "not_authenticated", "items": []}

        body = await self._safe_body_text()
        if await self._login_form_visible():
            self.connected = False
            self.status = "session_expired"
            return {"ok": False, "status": self.status, "items": []}

        # Conservative discovery only: do not click or submit anything.
        links = await self.page.locator("a").all()
        items = []
        for link in links:
            try:
                text = " ".join((await link.inner_text()).split())
                href = await link.get_attribute("href")
                lower = text.lower()
                if text and any(k in lower for k in ["cotação", "cotacao", "disputa"]):
                    items.append({"label": text[:200], "href": href})
            except Exception:
                continue

        return {
            "ok": True,
            "status": "authenticated",
            "url": self.page.url,
            "items": items[:100],
            "page_has_quotation_text": ("cotação" in body or "cotacao" in body),
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
