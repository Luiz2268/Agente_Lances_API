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

    async def start(self):
        if self.browser:
            return

        self.playwright = await async_playwright().start()

        self.browser = await self.playwright.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
        )

        self.context = await self.browser.new_context(
            viewport={"width": 1440, "height": 900},
            ignore_https_errors=True,
        )

        self.page = await self.context.new_page()

    async def connect(self, usuario: str, senha: str):
        await self.start()
        self.status = "connecting"

        try:
            await self.page.goto(
                S2GPR_LOGIN_URL,
                wait_until="domcontentloaded",
                timeout=60000,
            )

            html = (await self.page.content()).lower()

            if "captcha" in html or "recaptcha" in html:
                self.status = "human_action_required"
                return {
                    "connected": False,
                    "status": "human_action_required",
                    "reason": "captcha",
                }

            usuario_input = self.page.locator(
                'input[type="text"], '
                'input[name*="usuario" i], '
                'input[id*="usuario" i], '
                'input[name*="login" i], '
                'input[id*="login" i], '
                'input[name*="cpf" i], '
                'input[id*="cpf" i]'
            ).first

            senha_input = self.page.locator('input[type="password"]').first

            await usuario_input.wait_for(state="visible", timeout=15000)
            await senha_input.wait_for(state="visible", timeout=15000)

            await usuario_input.fill(usuario)
            await senha_input.fill(senha)

            # O S2GPR pode renderizar o comando de entrada como input, botão,
            # link JSF ou controle com texto. Tentamos os formatos normais
            # sem depender de um único seletor.
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

            # Fallback: em formulários JSF, Enter no campo senha normalmente
            # dispara a mesma ação do botão de autenticação.
            if not clicked:
                await senha_input.press("Enter")

            try:
                await self.page.wait_for_load_state(
                    "domcontentloaded",
                    timeout=15000,
                )
            except Exception:
                pass

            await self.page.wait_for_timeout(2500)

            current_url = self.page.url
            page_text = (await self.page.inner_text("body")).lower()

            if (
                "captcha" in page_text
                or "recaptcha" in page_text
                or "autenticação em dois fatores" in page_text
                or "código de verificação" in page_text
            ):
                self.connected = False
                self.status = "human_action_required"
                return {
                    "connected": False,
                    "status": "human_action_required",
                    "reason": "captcha_or_mfa",
                }

            # Se continuou na tela de login com os dois campos visíveis,
            # a autenticação não foi concluída.
            password_still_visible = False
            try:
                password_still_visible = (
                    await self.page.locator('input[type="password"]').count() > 0
                    and await self.page.locator('input[type="password"]').first.is_visible()
                )
            except Exception:
                pass

            if password_still_visible:
                self.connected = False
                self.status = "authentication_failed"
                return {
                    "connected": False,
                    "status": "authentication_failed",
                    "url": current_url,
                }

            self.connected = True
            self.status = "authenticated"

            return {
                "connected": True,
                "status": "authenticated",
                "url": current_url,
            }

        except Exception as exc:
            self.connected = False
            self.status = "error"

            return {
                "connected": False,
                "status": "error",
                "message": str(exc),
            }

    async def session_status(self):
        return {
            "connected": self.connected,
            "status": self.status,
            "url": self.page.url if self.page else None,
        }

    async def disconnect(self):
        if self.context:
            await self.context.close()

        if self.browser:
            await self.browser.close()

        if self.playwright:
            await self.playwright.stop()

        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self.connected = False
        self.status = "disconnected"

        return {
            "connected": False,
            "status": "disconnected",
        }


s2gpr_browser = S2GPRBrowser()
