import { PrismaClient } from "@prisma/client";

// One Prisma client per process. The API, the seed, and the stub worker all
// import this so connection handling is uniform.
export const prisma = new PrismaClient();

// Fastify serialises to JSON; BigInt has no JSON representation by default.
// Registering this once means byte_size and text_lines.id survive serialisation.
(BigInt.prototype as unknown as { toJSON: () => string }).toJSON = function () {
  return this.toString();
};
