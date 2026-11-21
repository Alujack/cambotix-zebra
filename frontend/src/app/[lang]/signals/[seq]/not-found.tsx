import Link from "next/link";

// Shown when the ledger number is not a published plan (an event row, a typo, or a number beyond the record).
export default function PlanNotFound() {
  return (
    <section className="py-16 text-center">
      <div className="label">404</div>
      <h1 className="mt-2 text-2xl font-bold">No published plan with that ledger number</h1>
      <p className="mt-2 text-sm text-muted">មិនមានផែនការដែលបានផ្សាយនៅលេខ ledger នេះទេ។ Only rows of kind &quot;published&quot; have a page; fills, targets and stops belong to their plan.</p>
      <Link href="/signals" className="btn-secondary mt-6">All signals · សញ្ញាទាំងអស់</Link>
    </section>
  );
}
