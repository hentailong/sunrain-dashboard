/** Shared dark chart styling: quiet axes, no horizontal grid, matching line/dot colors. */
export function chartTheme(option:any){
 const axes=(value:any)=>{
  const style=(axis:any)=>({...axis,nameTextStyle:{...axis.nameTextStyle,color:'#939daf'},splitLine:{...axis.splitLine,show:false},axisLabel:{...axis.axisLabel,color:'#939daf'},axisLine:{...axis.axisLine,lineStyle:{...axis.axisLine?.lineStyle,color:'#3b4351'}}});
  return Array.isArray(value)?value.map(style):value?style(value):value;
 };
 return {...option,
  ...(option.tooltip?{tooltip:{valueFormatter:(value:unknown)=>typeof value==='number'&&Number.isFinite(value)?value.toFixed(2):value==null?'—':String(value),...option.tooltip,backgroundColor:'#202631',borderColor:'#414957',textStyle:{...option.tooltip.textStyle,color:'#e1e4e9'},extraCssText:'box-shadow:0 5px 20px #0003;border-radius:8px;'}}:{}),
  ...(option.yAxis?{yAxis:axes(option.yAxis)}:{}),
  ...(option.xAxis?{xAxis:Array.isArray(option.xAxis)?option.xAxis.map((axis:any)=>({...axis,axisLine:{...axis.axisLine,lineStyle:{...axis.axisLine?.lineStyle,color:'#3b4351'}}})): {...option.xAxis,axisLine:{...option.xAxis.axisLine,lineStyle:{...option.xAxis.axisLine?.lineStyle,color:'#3b4351'}}}}:{}),
  ...(option.series?{series:option.series.map((series:any)=>({...series,...(series.type==='line'&&series.lineStyle?.color?{itemStyle:{...series.itemStyle,color:series.lineStyle.color}}:{})}))}:{}),
 };
}
