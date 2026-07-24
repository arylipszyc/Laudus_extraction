# Story 7.5: Notificaciones por email — parte email de FR37/FR41

Status: deferred

<!-- DIFERIDA POST-MVP (decisión Ary). Infraestructura 100% nueva (no hay envío de mail en el proyecto).
     El chip in-app (story 7.4) cubre el flujo de colaboración; el email es mejora, no bloqueante.
     Redactada para dejar el diseño listo, pero NO se implementa hasta que Ary la desbloquee.
     FR37/FR41 quedan PARCIALMENTE cubiertos (solo in-app vía 7.4) hasta que esta story se haga. -->

## Estado y cobertura

**DIFERIDA (post-MVP).** No se implementa en el Epic 7 inicial.

**Cobertura de FR37/FR41 mientras 7.5 esté diferida:** el chip in-app de la story 7.4 cubre la notificación **dentro de la app** (el contador ve un chip cuando el owner comenta; el owner ve un chip cuando el contador responde). Lo que **falta** hasta que 7.5 se haga: aviso **fuera de la app** (cuando el usuario no la tiene abierta). Dado que owner y contador entran a la app con regularidad, el equipo aceptó esto como una brecha menor. **FR37 y FR41 quedan marcados como PARCIALMENTE cubiertos (solo canal in-app)** hasta que esta story se implemente.

## Por qué está diferida

- **Infra 100% nueva.** El proyecto **no tiene hoy ningún envío de email**: no hay proveedor SMTP configurado, ni plantillas, ni tracking de entrega, ni manejo de rebotes/unsubscribe. Es una dependencia externa nueva (Render no provee mail; habría que integrar un proveedor: SendGrid/Resend/SES/etc.), con su propia gestión de secretos, límites de envío y modo de fallo.
- **El valor incremental sobre el chip es bajo en el MVP.** El chip in-app (7.4) ya resuelve el 90% del caso (ambos usan la app seguido). El email agrega alcance "cuando estás fuera", no una capacidad nueva de colaboración.
- **Regla de simplicidad del proyecto** (CLAUDE.md §2): no construir infra especulativa. El email entra cuando haya evidencia de que el chip no alcanza (ej. el owner tarda días en ver una respuesta).

## Story (para cuando se desbloquee)

As a **owner o contador del family office**,
I want **recibir un email cuando hay un comentario o respuesta nueva dirigida a mí en un hilo abierto**,
so that **me entere aunque no tenga la app abierta, sin depender de acordarme de entrar a revisar**.

## Alcance previsto (borrador — a validar al desbloquear)

- **FR37 (email al contador):** cuando el owner crea un comentario (7.1) o responde (7.2) un hilo, se dispara un email al contador con el contexto de la transacción + un link al inbox (`/comments`).
- **FR41 (email al owner):** cuando el contador responde (7.2), email al owner.
- **Anti-spam / batching:** no un email por evento si hay ráfaga — considerar un digest (ej. "tenés N comentarios nuevos") o un debounce por hilo. Decisión al desbloquear.
- **Respeta el estado del hilo:** un hilo resuelto (7.3) no dispara emails.
- **Opt-out:** el usuario debería poder desactivar los emails (o al menos un unsubscribe). Requerido si se usa un proveedor transaccional serio.

## Acceptance Criteria (borrador — no verificables aún)

1. **AC1 — Disparo de email al crear un comentario/respuesta dirigido al otro rol.** Un evento de comentario/respuesta en un hilo abierto encola un email al destinatario correcto (contador ← owner; owner ← contador), con contexto de la tx + link al inbox. El autor no se auto-notifica (consistente con 7.4 AC5).
2. **AC2 — Proveedor de email configurable + secretos por env.** La integración usa un proveedor transaccional vía variable de entorno (API key/SMTP), sin secretos hardcodeados, y **degrada con gracia** si el envío falla (loguea, no rompe el flujo de crear/responder — el comentario ya quedó persistido; el email es best-effort).
3. **AC3 — El email NO es la fuente de verdad.** El estado del hilo vive en `owner-comments.jsonl` (7.0). El email es una notificación de salida; un fallo de envío **nunca** afecta la persistencia del comentario ni el chip in-app.
4. **AC4 — Batching/anti-spam.** Múltiples eventos en poco tiempo sobre el mismo hilo no generan un email por evento (digest o debounce — mecanismo a definir).
5. **AC5 — Opt-out / unsubscribe.** El destinatario puede desactivar estos emails.
6. **AC6 — Tests.** El disparo se testea con el proveedor mockeado (no se manda mail real en CI); fallo del proveedor → el flujo de comentario sigue OK (AC2/AC3).

## Dev Notes (borrador)

- **Punto de enganche:** los mismos servicios que 7.1/7.2 ya escriben el comentario/respuesta (`create_comment`, `reply`) son el lugar natural para encolar el email — **después** de que `persist_and_commit` haya tenido éxito (el email notifica algo ya persistido, nunca al revés).
- **Destinatarios:** hoy no hay un directorio owner↔contador↔email más allá del `email` del JWT. Habrá que resolver a qué dirección va cada rol (¿config estática de "el contador es X, el owner es Y"? ¿tabla de usuarios?). Decisión al desbloquear — probablemente config estática por env dado el tamaño (un owner, un contador).
- **Degradación:** patrón del proyecto = best-effort que no rompe el camino crítico (como `git_commit_push` que degrada si el push falla). El email debe seguir esa filosofía: falla → log + sigue.
- **No** reusar nada de beancount/ledger acá — el email es puramente saliente, no toca el JSONL de comentarios más que para leer a quién notificar.

## References

- [Source: _bmad-output/implementation-artifacts/7-4-notificaciones-in-app.md] — parte in-app de FR37/FR41 (lo que 7.5 complementa); nota de "cobertura parcial".
- [Source: _bmad-output/implementation-artifacts/7-1-owner-crea-comentario.md] / [7-2-inbox-contador-respuesta.md] — puntos de enganche (`create_comment`, `reply`).
- [Source: _bmad-output/planning-artifacts/epics.md#Epic 7] — FR37, FR41 (parte email).
- [Source: CLAUDE.md §2] — simplicidad: no construir infra especulativa (justifica el defer).

## Decisiones de diseño para Ary (a resolver al desbloquear)

1. **Proveedor de email.** Resend / SendGrid / SES / SMTP directo. Depende de costo, residencia de datos y facilidad. Sin decidir.
2. **Batching vs. por-evento.** Digest ("N novedades") vs. un email por evento con debounce. Recomendado: digest simple para no spamear.
3. **Directorio de destinatarios.** Config estática por env (un owner, un contador) vs. tabla de usuarios. Recomendado: config estática dado el tamaño.
4. **¿Vale la pena vs. el chip?** La pregunta de fondo: ¿el chip in-app (7.4) resultó suficiente en la práctica? Desbloquear 7.5 solo si hay evidencia de que no.

## Dev Agent Record

### Agent Model Used

_(no implementada — story diferida)_

### Completion Notes List

_(no implementada)_

### File List

_(no implementada)_
