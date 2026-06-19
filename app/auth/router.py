import os
import resend
import jwt as pyjwt
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse

router = APIRouter()

# ─── Per-action copy ───────────────────────────────────────────────────────────
HOOK_EMAIL_TEMPLATES = {
    "signup": {
        "subject":      "Confirma tu correo — FyTic",
        "headline":     "Un paso más.",
        "body":         "Haz clic abajo para confirmar tu correo y activar tu acceso anticipado a FyTic. El enlace es válido por 24 horas.",
        "action_label": "Confirmar correo",
    },
    "recovery": {
        "subject":      "Restablece tu contraseña — FyTic",
        "headline":     "Recuperar acceso.",
        "body":         "Recibimos una solicitud para restablecer la contraseña de tu cuenta. Si no fuiste tú, ignora este correo; tu cuenta sigue segura.",
        "action_label": "Restablecer contraseña",
    },
    "magic_link": {
        "subject":      "Tu enlace de acceso — FyTic",
        "headline":     "Inicia sesión.",
        "body":         "Usa el botón de abajo para entrar a FyTic. Este enlace expira en 1 hora y solo funciona una vez.",
        "action_label": "Entrar a FyTic",
    },
    "invite": {
        "subject":      "Te invitaron a FyTic",
        "headline":     "Tienes una invitación.",
        "body":         "Alguien te invitó a unirte a FyTic, el sistema de investigación jurídica para despachos en México. Acepta antes de que el enlace expire.",
        "action_label": "Aceptar invitación",
    },
    "email_change_new": {
        "subject":      "Confirma tu nuevo correo — FyTic",
        "headline":     "Confirma el cambio.",
        "body":         "Recibimos una solicitud para actualizar el correo de tu cuenta. Confirma que este es tu nuevo correo.",
        "action_label": "Confirmar nuevo correo",
    },
}


def _build_html(action_url: str, headline: str, body_text: str, action_label: str) -> str:
    # All styles are inline — required for email client compatibility.
    # Colors match the FyTic design system: brand-ink bg, white text.
    return f"""<!DOCTYPE html>
<html lang="es" xmlns="http://www.w3.org/1999/xhtml">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <meta http-equiv="X-UA-Compatible" content="IE=edge" />
  <title>FyTic</title>
</head>
<body style="margin:0;padding:0;background-color:#07070f;-webkit-text-size-adjust:100%;-ms-text-size-adjust:100%;">
  <!-- Outer wrapper -->
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
         style="background-color:#07070f;min-width:100%;">
    <tr>
      <td align="center" style="padding:48px 16px;">

        <!-- Card -->
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
               style="max-width:520px;background-color:#0f0f1c;border-radius:20px;
                      border:1px solid rgba(255,255,255,0.08);overflow:hidden;">

          <!-- Header stripe -->
          <tr>
            <td style="padding:0;background:linear-gradient(135deg,#1a1a2e 0%,#0f0f1c 100%);
                       border-bottom:1px solid rgba(255,255,255,0.06);">
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
                <tr>
                  <td style="padding:28px 40px;">
                    <p style="margin:0;font-family:Georgia,'Times New Roman',serif;
                               font-size:22px;font-weight:400;letter-spacing:0.06em;
                               color:#f2f2f2;">
                      Fy<span style="font-style:italic;color:rgba(255,255,255,0.55);">Tic</span>
                    </p>
                    <p style="margin:4px 0 0;font-family:Arial,Helvetica,sans-serif;
                               font-size:10px;letter-spacing:0.38em;text-transform:uppercase;
                               color:rgba(255,255,255,0.28);">
                      Investigación jurídica · México
                    </p>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- Body -->
          <tr>
            <td style="padding:40px 40px 36px;">
              <!-- Headline -->
              <h1 style="margin:0 0 16px;font-family:Georgia,'Times New Roman',serif;
                          font-size:30px;font-weight:300;line-height:1.15;
                          color:#f2f2f2;letter-spacing:-0.01em;">
                {headline}
              </h1>
              <!-- Body text -->
              <p style="margin:0 0 32px;font-family:Arial,Helvetica,sans-serif;
                         font-size:15px;line-height:1.75;color:rgba(255,255,255,0.52);">
                {body_text}
              </p>
              <!-- CTA button -->
              <table role="presentation" cellpadding="0" cellspacing="0" border="0">
                <tr>
                  <td style="border-radius:100px;background-color:#f2f2f2;">
                    <a href="{action_url}"
                       style="display:inline-block;padding:14px 36px;
                              font-family:Arial,Helvetica,sans-serif;font-size:13px;
                              font-weight:600;letter-spacing:0.07em;text-transform:uppercase;
                              color:#07070f;text-decoration:none;border-radius:100px;">
                      {action_label}
                    </a>
                  </td>
                </tr>
              </table>
              <!-- Fallback link -->
              <p style="margin:24px 0 0;font-family:Arial,Helvetica,sans-serif;
                         font-size:11px;color:rgba(255,255,255,0.22);line-height:1.6;">
                Si el botón no funciona, copia y pega este enlace en tu navegador:<br/>
                <span style="color:rgba(255,255,255,0.38);word-break:break-all;">
                  {action_url}
                </span>
              </p>
            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td style="padding:20px 40px 28px;border-top:1px solid rgba(255,255,255,0.05);">
              <p style="margin:0;font-family:Arial,Helvetica,sans-serif;font-size:11px;
                         line-height:1.7;color:rgba(255,255,255,0.22);">
                Si no solicitaste esto, ignora este correo. Tu cuenta permanece segura.<br/>
                &copy; {_year()} FyTic &mdash; Monterrey y CDMX, México
              </p>
            </td>
          </tr>

        </table>
        <!-- /Card -->

      </td>
    </tr>
  </table>
</body>
</html>"""


def _year() -> int:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).year


def _verify_hook_signature(request: Request) -> None:
    secret = os.environ.get("SUPABASE_HOOK_SECRET", "")
    if not secret:
        return  # No secret configured — skip in dev
    auth_header = request.headers.get("Authorization", "")
    token = auth_header.removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(status_code=401, detail="Missing hook authorization")
    try:
        pyjwt.decode(token, secret, algorithms=["HS256"])
    except pyjwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid hook signature")


@router.post("/auth/welcome-email")
async def welcome_email_webhook(request: Request) -> JSONResponse:
    """Supabase Database Webhook — fires on INSERT into public.users.
    Sends a welcome email to OAuth users (email/password users get a confirmation
    email from the Send Email hook instead)."""

    # Verify bearer secret set in Supabase webhook headers
    secret = os.environ.get("SUPABASE_WEBHOOK_SECRET", "")
    if secret:
        auth = request.headers.get("Authorization", "")
        if auth.removeprefix("Bearer ").strip() != secret:
            raise HTTPException(status_code=401, detail="Invalid webhook secret")

    body = await request.json()
    record = body.get("record", {})

    to_email     = record.get("email", "")
    auth_provider = record.get("auth_provider", "email")

    # Only send welcome email to OAuth users — email/password users get a
    # confirmation email from the Send Email hook (avoid duplicate emails)
    if not to_email or auth_provider == "email":
        return JSONResponse({"ok": True})

    api_key = os.environ.get("RESEND_API_KEY", "")
    if not api_key:
        return JSONResponse({"ok": True})

    site_url = os.environ.get("FRONTEND_URL", "https://fytic.tech")

    resend.api_key = api_key
    resend.Emails.send({
        "from": "FyTic <noreply@fytic.tech>",
        "to": [to_email],
        "subject": "Bienvenido a FyTic",
        "html": _build_html(
            action_url=f"{site_url}/waitlist",
            headline="Bienvenido a FyTic.",
            body_text="Tu cuenta está lista. Únete a la lista de espera para obtener acceso anticipado y tu enlace único de referidos.",
            action_label="Ir a la lista de espera",
        ),
    })

    return JSONResponse({"ok": True})


@router.post("/auth/send-email")
async def send_email_hook(request: Request) -> JSONResponse:
    # IMPORTANT: always return 200 — any non-2xx causes Supabase to fail the entire signup
    try:
        _verify_hook_signature(request)

        body = await request.json()
        user       = body.get("user", {})
        email_data = body.get("email_data", {})

        to_email    = user.get("email", "")
        action_type = email_data.get("email_action_type", "signup")
        token_hash  = email_data.get("token_hash", "")
        redirect_to = email_data.get("redirect_to", "")

        template = HOOK_EMAIL_TEMPLATES.get(action_type)
        if not template or not to_email or not token_hash:
            return JSONResponse({})

        site_url   = os.environ.get("FRONTEND_URL", "https://fytic.tech")
        next_path  = redirect_to or f"{site_url}/"
        token_type = "email" if action_type == "signup" else action_type
        action_url = (
            f"{site_url}/auth/callback"
            f"?token_hash={token_hash}"
            f"&type={token_type}"
            f"&next={next_path}"
        )

        api_key = os.environ.get("RESEND_API_KEY", "")
        if not api_key:
            return JSONResponse({})

        resend.api_key = api_key
        resend.Emails.send({
            "from": "FyTic <noreply@fytic.tech>",
            "to": [to_email],
            "subject": template["subject"],
            "html": _build_html(
                action_url=action_url,
                headline=template["headline"],
                body_text=template["body"],
                action_label=template["action_label"],
            ),
        })
    except Exception:
        pass  # Never let hook errors block signup

    return JSONResponse({})
