import { notFound } from "next/navigation";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { HalftoneDivider } from "@/components/ui/halftone-divider";
import { Input } from "@/components/ui/input";
import { PosterCard } from "@/components/ui/poster-card";
import { StampBadge } from "@/components/ui/stamp-badge";
import { VinylSpinner } from "@/components/ui/vinyl-spinner";
import { Wordmark } from "@/components/ui/wordmark";
import { STATUS_MAP } from "@/lib/status";

// Dev-only: returns 404 in production builds
if (process.env.NODE_ENV === "production") {
  notFound();
}

const PALETTE = [
  { name: "--color-ink",        hex: "#1A1A1A", label: "Ink",        bg: "bg-ink",        text: "text-paper" },
  { name: "--color-ink-raised", hex: "#1E2323", label: "Ink Raised",  bg: "bg-ink-raised", text: "text-paper" },
  { name: "--color-teal",       hex: "#3E6868", label: "Teal",        bg: "bg-teal",       text: "text-paper" },
  { name: "--color-red",        hex: "#C94E44", label: "Red",         bg: "bg-red",        text: "text-paper" },
  { name: "--color-tan",        hex: "#C1AB85", label: "Tan",         bg: "bg-tan",        text: "text-ink"   },
  { name: "--color-paper",      hex: "#EFE6D2", label: "Paper",       bg: "bg-paper",      text: "text-ink"   },
  { name: "--color-teal-glow",  hex: "#7FAAA5", label: "Teal Glow",   bg: "bg-teal-glow",  text: "text-ink"   },
  { name: "--color-red-glow",   hex: "#E0776D", label: "Red Glow",    bg: "bg-red-glow",   text: "text-ink"   },
];

const TYPE_SCALE = [
  { name: "--text-xs",      label: "xs (11px)",       cls: "text-xs"      },
  { name: "--text-sm",      label: "sm (13px)",       cls: "text-sm"      },
  { name: "--text-base",    label: "base (15px)",     cls: "text-base"    },
  { name: "--text-md",      label: "md (17px)",       cls: "text-md"      },
  { name: "--text-lg",      label: "lg (20px)",       cls: "text-lg"      },
  { name: "--text-xl",      label: "xl (26px)",       cls: "text-xl"      },
  { name: "--text-display", label: "display (40px)",  cls: "text-display" },
];

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mb-12">
      <h2 className="mb-6 text-teal-glow">{title}</h2>
      {children}
    </section>
  );
}

export default function StyleguidePage() {
  return (
    <div className="content py-10">
      <div className="mb-10">
        <p className="eyebrow">Design System</p>
        <h1>Styleguide</h1>
        <p className="page-subtitle">All tokens, components, and status states in one place.</p>
      </div>

      {/* 1. Palette */}
      <Section title="Palette">
        <div className="grid grid-cols-4 gap-4">
          {PALETTE.map(({ name, hex, label, bg, text }) => (
            <div key={name} className="overflow-hidden rounded-card border-2 border-tan">
              <div className={`${bg} h-16`} />
              <div className="bg-ink-raised p-3">
                <p className={`text-xs font-bold ${text === "text-ink" ? "text-paper" : "text-paper"}`}>{label}</p>
                <p className="text-xs text-tan">{name}</p>
                <p className="text-xs text-tan">{hex}</p>
              </div>
            </div>
          ))}
        </div>
      </Section>

      {/* 2. Type scale */}
      <Section title="Type Scale">
        <div className="grid gap-4">
          {TYPE_SCALE.map(({ name, label, cls }) => (
            <div key={name} className="flex items-baseline gap-4">
              <span className="w-32 text-xs text-tan">{label}</span>
              <span className={`${cls} font-medium text-paper`}>The quick brown fox</span>
            </div>
          ))}
        </div>
      </Section>

      {/* 3. Primitives */}
      <Section title="Primitives">
        <div className="grid gap-6">
          {/* Buttons */}
          <div>
            <p className="mb-3 text-xs text-tan">Button variants</p>
            <div className="flex flex-wrap gap-3">
              <Button variant="solid">solid</Button>
              <Button variant="outline">outline</Button>
              <Button variant="quiet">quiet</Button>
              <Button variant="danger">danger</Button>
              <Button variant="ghost">ghost</Button>
            </div>
          </div>

          {/* Input + Select */}
          <div>
            <p className="mb-3 text-xs text-tan">Input &amp; Select</p>
            <div className="flex gap-4 max-w-md">
              <Input placeholder="Text input" />
              <select className="control h-10 rounded-md border border-tan bg-ink-raised px-3 text-sm text-paper">
                <option>Select option</option>
              </select>
            </div>
          </div>

          {/* Table */}
          <div>
            <p className="mb-3 text-xs text-tan">Table</p>
            <div className="surface">
              <div className="table-wrap">
                <table className="data-table">
                  <thead><tr><th scope="col">Agent</th><th scope="col">Status</th><th scope="col">Score</th></tr></thead>
                  <tbody>
                    <tr><td>PatchPilot</td><td>Passed</td><td className="metric-main" data-metric>92.4%</td></tr>
                    <tr><td>CodeBot</td><td>Failed</td><td className="metric-main" data-metric>61.0%</td></tr>
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </div>
      </Section>

      {/* 4. Status states */}
      <Section title="Status States">
        <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
          {Object.values(STATUS_MAP).map((entry) => (
            <div key={entry.status} className="surface p-4">
              <div className="relative z-10 flex items-center gap-2">
                <Badge status={entry.status}>
                  <entry.icon size={13} aria-hidden="true" />
                  {entry.label}
                </Badge>
              </div>
            </div>
          ))}
        </div>
      </Section>

      {/* 5. Visual components */}
      <Section title="Visual Components">
        <div className="grid gap-6">
          <div>
            <p className="mb-3 text-xs text-tan">Wordmark</p>
            <Wordmark size="lg" href="#" />
          </div>
          <div>
            <p className="mb-3 text-xs text-tan">PosterCard (teal shadow)</p>
            <PosterCard className="max-w-xs p-6">
              <p className="relative z-10 text-sm text-paper">PosterCard with double frame</p>
            </PosterCard>
          </div>
          <div>
            <p className="mb-3 text-xs text-tan">PosterCard (red shadow)</p>
            <PosterCard shadow="red" className="max-w-xs p-6">
              <p className="relative z-10 text-sm text-paper">Error emphasis variant</p>
            </PosterCard>
          </div>
          <div>
            <p className="mb-3 text-xs text-tan">StampBadge</p>
            <div className="flex gap-6">
              <StampBadge verdict="Passed" />
              <StampBadge verdict="Failed" />
            </div>
          </div>
          <div>
            <p className="mb-3 text-xs text-tan">VinylSpinner</p>
            <div className="flex items-center gap-6">
              <VinylSpinner size={32} />
              <VinylSpinner size={48} />
              <VinylSpinner size={64} />
            </div>
          </div>
          <div>
            <p className="mb-3 text-xs text-tan">HalftoneDivider</p>
            <HalftoneDivider color="var(--color-tan)" className="h-8" />
            <div className="mt-2" />
            <HalftoneDivider color="var(--color-red)" className="h-8" />
          </div>
        </div>
      </Section>
    </div>
  );
}
