import { useEffect, useRef, useState, useCallback } from 'react'
import * as d3 from 'd3'
import type { Agent } from '../../lib/types'
import { loadMeta, loadAgent } from '../../lib/data'
import { EMOTION_COLORS } from '../../lib/constants'
import { RelationshipCard } from './RelationshipCard'

interface Node extends d3.SimulationNodeDatum {
  id: string
  name: string
  emotion: string
}

interface Link extends d3.SimulationLinkDatum<Node> {
  fromId: string
  toId: string
  favorability: number
  trust: number
  understanding: number
  label: string
  recentInteractions: string[]
}

export function ForceGraph() {
  const svgRef = useRef<SVGSVGElement>(null)
  const [agents, setAgents] = useState<Agent[]>([])
  const [selectedEdge, setSelectedEdge] = useState<Link | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    loadMeta().then(async (meta) => {
      const loaded = await Promise.all(
        Object.keys(meta.agents).map((id) => loadAgent(id).catch(() => null))
      )
      setAgents(loaded.filter((a): a is Agent => a !== null))
      setLoading(false)
    })
  }, [])

  const drawGraph = useCallback(() => {
    if (!svgRef.current || agents.length === 0) return

    const svg = d3.select(svgRef.current)
    svg.selectAll('*').remove()

    const width = svgRef.current.clientWidth
    const height = 500

    // Build nodes
    const nodes: Node[] = agents.map((a) => ({
      id: a.agent_id,
      name: a.name,
      emotion: a.state.emotion,
    }))

    // Build edges (deduplicate: only keep A→B if |favorability|>5 or trust>5)
    const links: Link[] = []
    const seen = new Set<string>()
    for (const agent of agents) {
      for (const rel of Object.values(agent.relationships)) {
        if (Math.abs(rel.favorability) <= 5 && rel.trust <= 5) continue
        const key = [agent.agent_id, rel.target_id].sort().join('|')
        if (seen.has(key)) continue
        seen.add(key)
        links.push({
          source: agent.agent_id,
          target: rel.target_id,
          fromId: agent.agent_id,
          toId: rel.target_id,
          favorability: rel.favorability,
          trust: rel.trust,
          understanding: rel.understanding,
          label: rel.label,
          recentInteractions: rel.recent_interactions,
        })
      }
    }

    const g = svg.append('g')

    // Zoom
    svg.call(
      d3.zoom<SVGSVGElement, unknown>()
        .scaleExtent([0.3, 3])
        .on('zoom', (e) => g.attr('transform', e.transform))
    )

    const simulation = d3.forceSimulation(nodes)
      .force('link', d3.forceLink<Node, Link>(links).id((d) => d.id).distance(120))
      .force('charge', d3.forceManyBody().strength(-300))
      .force('center', d3.forceCenter(width / 2, height / 2))
      .force('collision', d3.forceCollide(40))

    // Draw edges
    const link = g.append('g')
      .selectAll('line')
      .data(links)
      .join('line')
      .attr('stroke', (d) => d.favorability >= 0 ? '#7AB893' : '#D94848')
      .attr('stroke-width', (d) => Math.max(1, Math.min(6, Math.abs(d.favorability) / 8)))
      .attr('stroke-dasharray', (d) => d.trust < 5 ? '4,4' : 'none')
      .attr('opacity', 0.6)
      .attr('cursor', 'pointer')
      .on('click', (_, d) => setSelectedEdge(d))

    // Draw nodes
    const drag = d3.drag<SVGGElement, Node>()
      .on('start', (e: d3.D3DragEvent<SVGGElement, Node, Node>, d) => {
        if (!e.active) simulation.alphaTarget(0.3).restart()
        d.fx = d.x
        d.fy = d.y
      })
      .on('drag', (e: d3.D3DragEvent<SVGGElement, Node, Node>, d) => {
        d.fx = e.x
        d.fy = e.y
      })
      .on('end', (e: d3.D3DragEvent<SVGGElement, Node, Node>, d) => {
        if (!e.active) simulation.alphaTarget(0)
        d.fx = null
        d.fy = null
      })

    const node = g.append('g')
      .selectAll<SVGGElement, Node>('g')
      .data(nodes)
      .join('g')
      .attr('cursor', 'pointer')
      .call(drag)

    node.append('circle')
      .attr('r', 20)
      .attr('fill', (d) => EMOTION_COLORS[d.emotion as keyof typeof EMOTION_COLORS] ?? '#B8B8B8')
      .attr('stroke', 'white')
      .attr('stroke-width', 2)

    node.append('text')
      .text((d) => d.name[0])
      .attr('text-anchor', 'middle')
      .attr('dy', '0.35em')
      .attr('fill', 'white')
      .attr('font-size', '14px')
      .attr('font-weight', 'bold')

    node.append('text')
      .text((d) => d.name)
      .attr('text-anchor', 'middle')
      .attr('dy', 36)
      .attr('fill', '#2c2c2c')
      .attr('font-size', '11px')

    simulation.on('tick', () => {
      link
        .attr('x1', (d) => (d.source as Node).x!)
        .attr('y1', (d) => (d.source as Node).y!)
        .attr('x2', (d) => (d.target as Node).x!)
        .attr('y2', (d) => (d.target as Node).y!)

      node.attr('transform', (d) => `translate(${d.x},${d.y})`)
    })
  }, [agents])

  useEffect(() => {
    drawGraph()
    const handleResize = () => drawGraph()
    window.addEventListener('resize', handleResize)
    return () => window.removeEventListener('resize', handleResize)
  }, [drawGraph])

  if (loading) {
    return (
      <div className="text-center py-20">
        <div className="inline-block w-6 h-6 border-2 border-amber border-t-transparent rounded-full animate-spin" />
      </div>
    )
  }

  return (
    <div>
      <h1 className="text-xl font-medium mb-4">关系网络</h1>
      <p className="text-sm text-ink-light mb-4">拖拽节点、滚轮缩放。点击连线查看关系详情。</p>

      <div className="relative bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden">
        <svg ref={svgRef} className="w-full" style={{ height: 500 }} />

        {selectedEdge && (
          <div className="absolute top-4 right-4">
            <button
              onClick={() => setSelectedEdge(null)}
              className="absolute -top-2 -right-2 z-10 w-6 h-6 rounded-full bg-gray-200 text-gray-600 text-xs flex items-center justify-center hover:bg-gray-300"
            >
              ✕
            </button>
            <RelationshipCard
              fromName={agents.find((a) => a.agent_id === selectedEdge.fromId)?.name ?? selectedEdge.fromId}
              toName={agents.find((a) => a.agent_id === selectedEdge.toId)?.name ?? selectedEdge.toId}
              favorability={selectedEdge.favorability}
              trust={selectedEdge.trust}
              understanding={selectedEdge.understanding}
              label={selectedEdge.label}
              recentInteractions={selectedEdge.recentInteractions}
            />
          </div>
        )}
      </div>
    </div>
  )
}
