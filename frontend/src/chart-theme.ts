/** Sunlit chart styling shared by overview and platform details. */
export function chartTheme(option:any){
 const ink='#78858b',line='#d6dddc';
 const axes=(value:any)=>{
  const style=(axis:any)=>({...axis,nameTextStyle:{...axis.nameTextStyle,color:ink},splitLine:{...axis.splitLine,show:false},axisLabel:{...axis.axisLabel,color:ink},axisLine:{...axis.axisLine,lineStyle:{...axis.axisLine?.lineStyle,color:line}}});
  return Array.isArray(value)?value.map(style):value?style(value):value;
 };
 const colors:Record<string,string>={'#a498e5':'#79969b','#82a7ed':'#5d8fa9','#efbd69':'#b28c49','#ed947d':'#ba886a','#6bbad2':'#658c9c','#2897d6':'#6b95a5','#ffc458':'#ad9870','#c9b78e':'#618a9c'};
 const legend=(value:any)=>({...value,textStyle:{...value.textStyle,color:ink},inactiveColor:'#c5d4cd'});
 return {...option,textStyle:{...option.textStyle,color:ink},
  ...(option.legend?{legend:Array.isArray(option.legend)?option.legend.map(legend):legend(option.legend)}:{}),
  ...(option.tooltip?{tooltip:{valueFormatter:(value:unknown)=>typeof value==='number'&&Number.isFinite(value)?value.toFixed(2):value==null?'—':String(value),...option.tooltip,backgroundColor:'#fffffd',borderColor:'#cbded2',textStyle:{...option.tooltip.textStyle,color:'#455b66'},extraCssText:'box-shadow:0 5px 20px #385d4920;border-radius:10px;'}}:{}),
  ...(option.yAxis?{yAxis:axes(option.yAxis)}:{}),
  ...(option.xAxis?{xAxis:axes(option.xAxis)}:{}),
  ...(option.series?{series:option.series.map((series:any)=>{
   const original=series.lineStyle?.color||series.itemStyle?.color;
   const color=series.name==='昨日'?'#8ba3ab':series.yAxisIndex===1?'#ad9870':colors[original]||'#658996';
   return {...series,itemStyle:{...series.itemStyle,color,...(series.itemStyle?.borderColor?{borderColor:color}:{})},lineStyle:{...series.lineStyle,color},...(series.areaStyle?{areaStyle:{...series.areaStyle,color,opacity:.08}}:{})};
  })}:{}),
 };
}
