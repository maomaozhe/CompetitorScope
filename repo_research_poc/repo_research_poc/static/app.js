const $ = (id) => document.getElementById(id);
const statusLabels = { ok: '引用已核验', error: '运行失败', invalid_citations: '引用未通过' };
let activeJob = null;

async function getJSON(path, options) {
  const response = await fetch(path, options);
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || `请求失败 (${response.status})`);
  return data;
}

function node(tag, className, content) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (content !== undefined) element.textContent = String(content);
  return element;
}

function clear(id) { $(id).replaceChildren(); }
function show(id, visible) { $(id).hidden = !visible; }
function badge(label, kind) {
  const element = $('result-badge');
  element.textContent = label;
  element.className = `badge ${kind}`;
}
function message(value) {
  $('form-message').textContent = value;
  show('form-message', Boolean(value));
}

function renderResult(result) {
  show('empty-result', false);
  show('result-content', true);
  const valid = result.status === 'ok';
  badge(statusLabels[result.status] || result.status || '未知状态', valid ? 'ok' : 'error');
  const meta = [result.run_id && `ID ${result.run_id.slice(0, 12)}`,
    result.duration_ms != null && `${Math.round(result.duration_ms / 1000)} 秒`,
    result.tool_calls && `${result.tool_calls.length} 次工具调用`].filter(Boolean);
  $('result-meta').textContent = meta.join('  /  ');

  show('answer-block', valid && Boolean(result.answer));
  $('answer-text').textContent = valid ? (result.answer || '') : '';
  const citations = valid ? (result.citations || []) : [];
  show('citations-block', citations.length > 0);
  $('citation-count').textContent = `(${citations.length})`;
  clear('citations-list');
  for (const cite of citations) {
    const box = node('div', 'citation');
    box.append(node('div', 'citation-path', `${cite.path}:${cite.start_line}-${cite.end_line}`));
    box.append(node('pre', '', cite.quote));
    $('citations-list').append(box);
  }

  const unresolved = result.unresolved_questions || [];
  show('unresolved-block', unresolved.length > 0);
  clear('unresolved-list');
  for (const item of unresolved) $('unresolved-list').append(node('li', '', item));

  const diagnostics = [
    ...(result.errors || []).map((item) => `${item.type}: ${item.message}`),
    ...(result.citation_issues || []).map((item) => `${item.code}: ${item.detail}`),
    ...(result.parse_attempts || []).map((item, index) => `JSON 解析第 ${index + 1} 次失败：${item.reason}（${item.output_chars} 字符）`),
  ];
  show('diagnostics-block', diagnostics.length > 0);
  clear('diagnostics-list');
  for (const item of diagnostics) $('diagnostics-list').append(node('div', 'diagnostic', item));
  $('audit-content').replaceChildren(node('pre', '', JSON.stringify({
    snapshot_path: result.snapshot_path, commit_sha: result.commit_sha,
    model: result.model, source_manifest_sha256: result.source_manifest_sha256,
    tool_calls: result.tool_calls, citation_attempts: result.citation_attempts,
  }, null, 2)));
  $('result').scrollIntoView({ behavior: 'smooth', block: 'start' });
}

async function loadHistory() {
  try {
    const { runs } = await getJSON('/api/runs');
    clear('history-list');
    if (!runs.length) {
      $('history-list').append(node('p', 'history-empty', '暂无运行记录。完成一次研究后会显示在这里。'));
      return;
    }
    for (const run of runs) {
      const row = node('button', 'history-item');
      row.type = 'button';
      row.append(node('span', `history-status ${run.status === 'ok' ? '' : 'error'}`, statusLabels[run.status] || run.status));
      row.append(node('span', 'history-question', run.question || run.run_id));
      row.append(node('span', 'history-time', run.started_at ? new Date(run.started_at).toLocaleString('zh-CN') : '—'));
      row.append(node('span', 'history-duration', run.duration_ms == null ? '—' : `${Math.round(run.duration_ms / 1000)} s`));
      row.addEventListener('click', async () => {
        try { renderResult(await getJSON(`/api/runs/${run.run_id}`)); }
        catch (error) { message(error.message); }
      });
      $('history-list').append(row);
    }
  } catch (error) { $('history-list').textContent = `读取记录失败：${error.message}`; }
}

async function pollJob(jobId) {
  if (activeJob !== jobId) return;
  try {
    const job = await getJSON(`/api/jobs/${jobId}`);
    if (job.status === 'running') {
      setTimeout(() => pollJob(jobId), 1500);
      return;
    }
    activeJob = null;
    $('submit-button').disabled = false;
    if (job.status === 'complete') {
      renderResult(job.result);
      await loadHistory();
    } else {
      message(job.error || '运行失败');
      badge('运行失败', 'error');
    }
  } catch (error) {
    activeJob = null;
    $('submit-button').disabled = false;
    message(error.message);
  }
}

$('research-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  if (activeJob) return;
  message('');
  const payload = {
    snapshot: $('snapshot').value.trim(),
    commit_sha: $('commit').value.trim(),
    question: $('question').value.trim(),
  };
  try {
    $('submit-button').disabled = true;
    const { job_id } = await getJSON('/api/jobs', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
    });
    activeJob = job_id;
    badge('研究进行中', 'running');
    show('empty-result', true);
    show('result-content', false);
    $('empty-result').querySelector('h3').textContent = '正在检索与核验源码';
    $('empty-result').querySelector('p').textContent = '真实仓库可能需要数分钟。页面会自动更新结果。';
    pollJob(job_id);
  } catch (error) {
    $('submit-button').disabled = false;
    message(error.message);
  }
});

$('refresh-history').addEventListener('click', loadHistory);
getJSON('/api/config').then((config) => {
  $('model-name').textContent = `MODEL / ${config.model || '未配置'}`;
}).catch(() => { $('model-name').textContent = 'MODEL / 配置不可用'; });
loadHistory();
