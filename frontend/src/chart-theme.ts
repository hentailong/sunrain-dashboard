/** Sunlit chart styling shared by overview and platform details. */
export function chartTheme(option:any){
 const ink='#668079',line='#ccded5';
 const axes=(value:any)=>{
  const style=(axis:any)=>({...axis,nameTextStyle:{...axis.nameTextStyle,color:ink},splitLine:{...axis.splitLine,show:false},axisLabel:{...axis.axisLabel,color:ink},axisLine:{...axis.axisLine,lineStyle:{...axis.axisLine?.lineStyle,color:line}}});
  return Array.isArray(value)?value.map(style):value?style(value):value;
 };
 const colors:Record<string,string>={'#a498e5':'#719b8f','#82a7ed':'#5d8fa9','#efbd69':'#b28c49','#ed947d':'#ba886a','#6bbad2':'#418e99','#2897d6':'#4b9da4','#ffc458':'#b8964c','#c9b78e':'#3e9187'};
 const legend=(value:any)=>({...value,textStyle:{...value.textStyle,color:ink},inactiveColor:'#c5d4cd'});
 return {...option,textStyle:{...option.textStyle,color:ink},
  ...(option.legend?{legend:Array.isArray(option.legend)?option.legend.map(legend):legend(option.legend)}:{}),
  ...(option.tooltip?{tooltip:{valueFormatter:(value:unknown)=>typeof value==='number'&&Number.isFinite(value)?value.toFixed(2):value==null?'—':String(value),...option.tooltip,backgroundColor:'#fffffc',borderColor:'#cbded2',textStyle:{...option.tooltip.textStyle,color:'#355f55'},extraCssText:'box-shadow:0 5px 20px #385d4920;border-radius:10px;'}}:{}),
  ...(option.yAxis?{yAxis:axes(option.yAxis)}:{}),
  ...(option.xAxis?{xAxis:axes(option.xAxis)}:{}),
  ...(option.series?{series:option.series.map((series:any)=>{
   const original=series.lineStyle?.color||series.itemStyle?.color;
   const color=series.name==='昨日'?'#8ba3ab':series.yAxisIndex===1?'#b8964c':colors[original]||'#468e88';
   return {...series,itemStyle:{...series.itemStyle,color,...(series.itemStyle?.borderColor?{borderColor:color}:{})},lineStyle:{...series.lineStyle,color},...(series.areaStyle?{areaStyle:{...series.areaStyle,color,opacity:.08}}:{})};
  })}:{}),
 };
}
