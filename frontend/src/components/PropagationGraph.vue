<template>
  <div>
    <div class="propagation-toolbar">
      <el-alert :title="data?.summary?.coverage_notice || '仅反映当前已采集公开数据'" type="warning" show-icon :closable="false" />
      <el-switch v-model="showOrdinary" active-text="展开普通节点" />
    </div>
    <div v-if="!visibleNodes.length" class="propagation-empty">当前数据不足，暂未形成可信传播关系。</div>
    <div ref="chartEl" class="propagation-chart" />
  </div>
</template>
<script setup>
import * as echarts from 'echarts';
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue';
const props=defineProps({data:{type:Object,default:()=>({graph:{nodes:[],links:[]}})}});
const chartEl=ref(); const showOrdinary=ref(false); let chart;
const colors={origin_candidate:'#ef4444',influencer_amplification:'#8b5cf6',media_intervention:'#2563eb',official_response:'#eab308',peak_content:'#f97316',turning_point:'#f97316',ordinary:'#94a3b8'};
const visibleNodes=computed(()=> (props.data?.graph?.nodes||[]).filter(n=>showOrdinary.value||n.is_key_node));
function render(){if(!chartEl.value)return; chart ||= echarts.init(chartEl.value); const nodes=visibleNodes.value; const ids=new Set(nodes.map(n=>n.id)); const platforms=[...new Set(nodes.map(n=>n.platform))]; const times=nodes.map(n=>Date.parse(n.publish_time||'')).filter(Number.isFinite); const start=Math.min(...times,0); const graphNodes=nodes.map((n,i)=>({...n,x:Number.isFinite(Date.parse(n.publish_time||''))?(Date.parse(n.publish_time)-start)/3600000:i*12,y:platforms.indexOf(n.platform)*90,itemStyle:{color:colors[n.node_type]||colors.ordinary}})); const links=(props.data?.graph?.links||[]).filter(e=>ids.has(e.source)&&ids.has(e.target)).map(e=>({...e,lineStyle:{type:e.evidence_type==='explicit'?'solid':'dashed',width:e.evidence_type==='explicit'?3:1.5,opacity:.75,color:e.evidence_type==='explicit'?'#334155':'#94a3b8'}})); chart.setOption({tooltip:{formatter(p){if(p.dataType==='edge')return `${p.data.evidence_type==='explicit'?'明确关系':'推测关系'}<br/>置信度 ${(p.data.confidence*100).toFixed(0)}%<br/>${(p.data.evidence||[]).join('<br/>')}`; return `<b>${p.data.title}</b><br/>${p.data.name} · ${p.data.platform}<br/>${p.data.publish_time||'时间未知'}<br/>${(p.data.key_node_reasons||[]).join('、')}`}},legend:{data:Object.keys(colors).map(name=>({name}))},series:[{type:'graph',layout:'none',roam:true,label:{show:true,position:'right',formatter:'{b}'},data:graphNodes.map(n=>({...n,name:n.name})),links,categories:Object.keys(colors).map(name=>({name,itemStyle:{color:colors[name]}})),edgeSymbol:['none','arrow'],edgeSymbolSize:8}]},true)}
watch([()=>props.data,showOrdinary],()=>nextTick(render),{deep:true}); onMounted(()=>{render();window.addEventListener('resize',render)}); onBeforeUnmount(()=>{window.removeEventListener('resize',render);chart?.dispose()});
</script>
