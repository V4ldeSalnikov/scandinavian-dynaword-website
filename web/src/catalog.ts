export type CorpusSource = {id:string;name:string;domain:string;records:number;tokens:number;annotated:number|null;quality:Record<string,number>|null;url:string};
export type Corpus = {id:string;name:string;language_code:string;repo:string;revision:string;version:string;url:string;records:number;tokens:number;annotated:number|null;quality:Record<string,number>|null;tokenizer:string;notes:string[];stats_url:string;sources:CorpusSource[];domains:{name:string;records:number;tokens:number;sources:number}[]};
export type Catalog = {schema_version:number;generated_at:string;datasets:Corpus[];indexed_danish:{version:string;revision:string;records:number;tokens:number;sources:number}};
export const language = (d:Corpus) => d.name.replace(" Dynaword", "");
export const languageColors:Record<string,string> = {danish:"#b7192d",norwegian:"#4669a0",swedish:"#bd8e22",icelandic:"#378987",faroese:"#8161a4"};
