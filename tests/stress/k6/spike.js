import encoding from 'k6/encoding';
import http from 'k6/http';
import { check } from 'k6';
import { SharedArray } from 'k6/data';

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8080';
const STRICT = __ENV.K6_STRICT === '1';

const PDFS = new SharedArray('pdfs', function () {
  return [
    { name: 'small.pdf', data: encoding.b64encode(open('../pdfs/small.pdf', 'b')) },
    { name: 'medium.pdf', data: encoding.b64encode(open('../pdfs/medium.pdf', 'b')) },
    { name: 'large.pdf', data: encoding.b64encode(open('../pdfs/large.pdf', 'b')) },
    { name: 'xlarge.pdf', data: encoding.b64encode(open('../pdfs/xlarge.pdf', 'b')) },
  ];
});

const VU_INDEX = __VU === 0 ? 0 : (__VU - 1) % PDFS.length;
const PDF = {
  name: PDFS[VU_INDEX].name,
  data: encoding.b64decode(PDFS[VU_INDEX].data, 'std', 'd'),
};
const HEAVY_PDFS = ['large.pdf', 'xlarge.pdf'];

export const options = {
  scenarios: {
    spike: {
      executor: 'ramping-vus',
      startVUs: 0,
      stages: [
        { duration: '10s', target: 100 },
        { duration: '20s', target: 100 },
        { duration: '10s', target: 0 },
      ],
      gracefulRampDown: '10s',
    },
  },
  summaryTrendStats: ['avg', 'min', 'med', 'p(90)', 'p(95)', 'p(99)', 'max'],
  thresholds: {
    http_req_failed: ['rate<0.01'],
    checks: ['rate>0.99'],
    ...(STRICT ? { http_req_duration: ['p(95)<10000', 'p(99)<15000'] } : {}),
  },
  tags: {
    suite: 'k6-spike',
  },
};

export default function () {
  const heavy = HEAVY_PDFS.includes(PDF.name);

  const response = http.post(
    `${BASE_URL}/extract`,
    { file: http.file(PDF.data, PDF.name, 'application/pdf') },
    {
      tags: { endpoint: 'extract' },
      timeout: '60s',
      responseType: heavy ? 'none' : 'text',
    },
  );

  check(response, {
    'status is 200': (res) => res.status === 200,
  });

  if (!heavy) {
    check(response, {
      'json contract': (res) => {
        if (res.status !== 200) {
          return false;
        }
        try {
          const body = res.json();
          return typeof body.content === 'string' && Number.isInteger(body.page_count);
        } catch (_error) {
          return false;
        }
      },
    });
  }
}
