'use strict';
const rows = [{period:'2026-10',amount:12},{period:'2026-10',amount:8},{period:'2026-09',amount:99}];
const period = document.querySelector('[data-target="period"]');
period.addEventListener('change', () => {
  document.body.dataset.inputEvents = String(Number(document.body.dataset.inputEvents) + 1);
  document.querySelector('[data-target="total"]').textContent = String(rows.filter(row=>row.period===period.value).reduce((n,row)=>n+row.amount,0));
});
document.querySelector('[data-target="export"]').addEventListener('click', async () => {
  const instanceId = document.body.dataset.instanceId;
  try {
    const response = await fetch('/api/export?'+new URLSearchParams({period:period.value,instanceId}));
    if (!response.ok || response.headers.get('X-Owned-Instance') !== instanceId) throw new Error('export_rejected');
    const blob = await response.blob();
    document.querySelector('[data-target="receipt"]').textContent = response.headers.get('X-Owned-Receipt');
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = 'owned-report.csv';
    link.click();
    setTimeout(()=>URL.revokeObjectURL(link.href), 1000);
  } catch (_error) { document.body.dataset.exportError = 'true'; }
});
