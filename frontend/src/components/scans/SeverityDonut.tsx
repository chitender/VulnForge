import { Cell, Legend, Pie, PieChart, Tooltip } from 'recharts'
import { SEVERITY_COLORS, SEVERITY_ORDER } from '../../lib/severity'

interface Props {
  summary: Record<string, number>
}

export function SeverityDonut({ summary }: Props) {
  const data = SEVERITY_ORDER
    .filter(s => (summary[s] ?? 0) > 0)
    .map(s => ({ name: s, value: summary[s] ?? 0, color: SEVERITY_COLORS[s] }))

  if (data.length === 0) {
    return <p className="text-slate-500 text-sm">No vulnerabilities found</p>
  }

  return (
    <PieChart width={240} height={240}>
      <Pie data={data} cx={120} cy={120} innerRadius={60} outerRadius={100} dataKey="value">
        {data.map(entry => (
          <Cell key={entry.name} fill={entry.color} />
        ))}
      </Pie>
      <Tooltip
        contentStyle={{
          backgroundColor: '#1e293b',
          border: '1px solid #334155',
          color: '#f1f5f9',
        }}
      />
      <Legend
        formatter={value => (
          <span className="text-slate-300 text-xs">{value}</span>
        )}
      />
    </PieChart>
  )
}
