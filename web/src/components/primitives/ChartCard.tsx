import { Card } from "./Card";
import { SectionHeader } from "./SectionHeader";

interface Props {
  title: string;
  hint?: string;
  right?: React.ReactNode;
  children: React.ReactNode;
}

export function ChartCard({ title, hint, right, children }: Props) {
  return (
    <Card className="p-4">
      <SectionHeader title={title} hint={hint} right={right} />
      {children}
    </Card>
  );
}
