'use strict';
// Owned fixture: these counters are updated only by actual browser input events.
document.body.dataset.inputEvents = '0';
for (const input of document.querySelectorAll('input')) {
  input.addEventListener('input', () => {
    document.body.dataset.inputEvents = String(Number(document.body.dataset.inputEvents) + 1);
    if (document.body.dataset.identityAfterInput === 'true') document.body.dataset.instanceId = 'changed-owned-instance';
    if (document.body.dataset.securityProbe === 'true') {
      fetch('/api/redirect').catch(()=>{});
      fetch(document.body.dataset.testOffOrigin).catch(()=>{});
      window.open('/health','_blank');
    }
  });
}
document.querySelector('#entry').addEventListener('submit', async event => {
  event.preventDefault();
  const name = document.querySelector('[data-target="name"]').value;
  const quantity = Number(document.querySelector('[data-target="quantity"]').value);
  const instanceId = document.body.dataset.instanceId;
  try {
    const response = await fetch('/api/save', {method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({name,quantity,instanceId,inputEvents:Number(document.body.dataset.inputEvents)})});
    if (!response.ok) throw new Error('save_rejected');
    const reply = await response.json();
    if (reply.instanceId !== instanceId || !Number.isInteger(reply.receipt)) throw new Error('receipt_rejected');
    document.querySelector('[data-target="receipt"]').textContent = String(reply.receipt);
  } catch (_error) { document.body.dataset.saveError = 'true'; }
});
