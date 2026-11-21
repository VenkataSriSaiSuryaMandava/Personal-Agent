import { ShieldCheck } from "lucide-react";

interface ApprovalsProps {
  onOpen: () => void;
}

export default function Approvals({
  onOpen,
}: ApprovalsProps) {
  return (
    <section className="panel">
      <div className="panel-heading">
        <h2>Privacy &amp; approvals</h2>
        <ShieldCheck size={19} />
      </div>

      <div className="empty-state">
        <strong>No pending approval requests</strong>
        <p>
          External actions and personal data access are
          not enabled in this preview.
        </p>
      </div>

      <button className="secondary-button" onClick={onOpen}>
        View permissions
      </button>
    </section>
  );
}
