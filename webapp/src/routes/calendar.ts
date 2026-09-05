import type { FastifyInstance } from "fastify";
import { z } from "zod";
import { Prisma } from "@prisma/client";
import { prisma } from "../db.js";
import { getWorkspaceId } from "../lib/workspace.js";
import { badRequest, notFound } from "../lib/errors.js";
import { serializeCalendarEvent } from "../lib/serialize.js";
import { CONFIDENCE_TIERS } from "../lib/domain.js";

function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}
function addDays(iso: string, days: number): string {
  const d = new Date(iso + "T00:00:00Z");
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}
function tierRank(t: string): number {
  const i = CONFIDENCE_TIERS.indexOf(t as (typeof CONFIDENCE_TIERS)[number]);
  return i === -1 ? CONFIDENCE_TIERS.length : i;
}

export async function registerCalendarRoutes(app: FastifyInstance) {
  const query = z.object({
    from: z.string().optional(),
    to: z.string().optional(),
    // A tier floor: include only events at least this confident (§9, "confirmed
    // dates only"). Lower rank = more confident.
    minConfidence: z.enum(CONFIDENCE_TIERS).optional(),
    // "active" = open + acknowledged (dismissed hidden by default, §9).
    status: z.enum(["active", "open", "acknowledged", "dismissed", "all"]).optional().default("active"),
  });

  app.get("/api/calendar", async (req) => {
    const workspaceId = await getWorkspaceId();
    const q = query.parse(req.query);
    const today = todayIso();
    const to = q.to ?? addDays(today, 90);

    const where: Prisma.CalendarEventWhereInput = { workspaceId };
    if (q.status === "all") {
      /* no status filter */
    } else if (q.status === "active") {
      where.status = { in: ["open", "acknowledged"] }; // dismissed hidden by default
    } else {
      where.status = q.status;
    }

    const rows = await prisma.calendarEvent.findMany({ where });

    // Effective date = the date the user must act on (falls back to event date).
    const effective = (e: (typeof rows)[number]) =>
      (e.actionByDate ?? e.eventDate).toISOString().slice(0, 10);

    let events = rows.filter((e) => {
      const eff = effective(e);
      if (eff > to) return false; // beyond the forward window
      if (q.from && eff < q.from) return false;
      if (q.minConfidence && tierRank(e.confidenceTier) > tierRank(q.minConfidence)) return false;
      return true;
    });

    events.sort((a, b) => {
      const ea = effective(a);
      const eb = effective(b);
      if (ea !== eb) return ea < eb ? -1 : 1;
      const da = a.eventDate.toISOString();
      const db = b.eventDate.toISOString();
      return da < db ? -1 : da > db ? 1 : 0;
    });

    return { today, to, events: events.map(serializeCalendarEvent) };
  });

  const patchBody = z.object({ status: z.enum(["open", "acknowledged", "dismissed"]) });
  app.patch<{ Params: { id: string } }>("/api/calendar/:id", async (req) => {
    const body = patchBody.safeParse(req.body);
    if (!body.success) throw badRequest("status must be open, acknowledged, or dismissed.");
    const existing = await prisma.calendarEvent.findUnique({ where: { id: req.params.id } });
    if (!existing) throw notFound("Calendar event not found.");
    const updated = await prisma.calendarEvent.update({
      where: { id: req.params.id },
      data: { status: body.data.status },
    });
    return serializeCalendarEvent(updated);
  });
}
