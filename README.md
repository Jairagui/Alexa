# Alexa – Skill Coach
## video
https://youtu.be/NTTkfybJftQ

---
## Archivos del proyecto

---

### **Lambda_function.py**

Para nosotros, el archivo lambda_function.py representa el núcleo de la skill en 
AWS Lambda porque es justo ahí donde recibimos todas las peticiones de Alexa y 
determinamos el flujo a seguir según el intent que se active. En este archivo 
concentramos la definición de los handlers esenciales, empezando por el de 
bienvenida y el menú, pasando por el que recopila los datos del usuario como 
peso y estatura para generar la rutina, hasta los encargados de gestionar, 
borrar o guardar los planes directamente en S3.

A nivel de diseño lo pensamos como un orquestador que nos permite mantener una 
separación clara entre la capa de conversación y la lógica de negocio más 
compleja. De esta forma, el archivo actúa como un puente que traduce la entrada 
del usuario, invoca a nuestra fachada y estrategias, y finalmente estructura la 
respuesta verbal de Alexa, lo cual nos facilita mucho el mantenimiento del 
código sin mezclar responsabilidades.

---

### **rutina_servicio.py**

En este archivo ubicamos la clase RoutineFacade que es básicamente la encargada 
de generar la rutina completa a partir de los datos que recibimos del usuario 
como el nivel el tipo el peso la estatura y la estrategia de modo. Aquí es 
donde centralizamos toda la lógica de negocio ya que esta clase coordina el 
cálculo del IMC la selección de los sets de ejercicios adecuados y el armado 
final del plan con calentamiento y descansos.

Nuestra intención fue aplicar el patrón Facade para exponer un único método 
sencillo hacia el exterior ocultando toda la complejidad interna de cómo se 
eligen y combinan los ejercicios. Esto nos ayuda muchísimo a limpiar el código 
en la función principal porque lambda_function.py solo tiene que pedir la rutina 
y esperar el resultado listo sin tener que preocuparse por los detalles técnicos 
de la construcción del entrenamiento.

---

### **modos_rutina.py**

En este archivo concentramos la lógica para los modos de rutina ya sea manual o 
aleatorio mediante la función crear_strategy que devuelve el comportamiento 
adecuado según lo que pida el usuario. Aquí es donde implementamos un patrón 
Strategy para evitar llenar el código de condicionales dispersos y en su lugar 
centralizar la decisión de cómo se seleccionan los ejercicios ya sea respetando 
totalmente la configuración o variando el contenido.

Dentro del flujo general esto nos permite que cuando la lambda detecta el modo 
simplemente obtenga la estrategia y se la pase a la fachada manteniendo la 
flexibilidad de cambiar la lógica interna de los modos sin afectar el resto del 
sistema.

---

### **rutina_creador.py**

En este archivo nos encargamos de armar la rutina paso a paso ya que su función 
principal no es elegir los ejercicios sino decidir cómo se acomodan y en qué 
orden van. Aquí recibimos los bloques de calentamiento ejercicios y vuelta a la 
calma para insertar los descansos necesarios y ajustar la duración de cada 
actividad según el nivel del usuario generando una estructura final con los 
textos que dirá Alexa.

Lo diseñamos siguiendo un enfoque muy parecido al patrón Builder porque vamos 
construyendo el objeto rutina agregando sus partes en orden y aplicando reglas 
específicas de tiempo y descanso. Dentro del flujo general este módulo recibe 
los ejercicios seleccionados por la fachada y se encarga de empaquetarlos en un 
formato listo para ser narrado.

---

### **selector_sets.py**

En este módulo concentramos la responsabilidad de elegir el set de ejercicios 
correcto basándonos en datos clave como el tipo de rutina el nivel y la 
condición física del usuario para buscar la mejor coincidencia en nuestro 
archivo de configuraciones. Lo diseñamos funcionando como una pequeña Factory 
que dado un contexto específico nos devuelve el grupo de ejercicios adecuado 
asegurándonos de tener siempre una respuesta o una variante cercana si no hay 
coincidencia directa.

Dentro del flujo general esto nos permite mantener aislada la lógica de 
selección de modo que la fachada nos llama para obtener la lista cruda de 
ejercicios y si el día de mañana queremos modificar qué actividades tocan por 
nivel solo tenemos que ajustar este componente o el json sin afectar el resto 
del sistema.

---

### **imc.py**

En este archivo encapsulamos toda la lógica relacionada con el IMC 
encargándonos tanto de calcular el valor numérico a partir del peso y la 
estatura como de clasificar el resultado en sus respectivas categorías de 
salud. Aquí aplicamos estrictamente el principio de Responsabilidad Única 
logrando que el módulo se enfoque solo en las métricas físicas sin saber nada 
de Alexa ni de la infraestructura lo que nos facilita el mantenimiento si 
alguna vez cambian los criterios médicos.

Dentro del flujo general tanto la función principal como la fachada utilizan 
este componente para determinar la condición del usuario y con esa información 
ajustar la intensidad o los descansos de la rutina permitiendo que el 
entrenamiento se adapte dinámicamente si detectamos sobrepeso u otra condición.

---

### **app.py**

app.pyEn este archivo establecimos el punto de entrada local para el proyecto cuyo 
objetivo principal es permitirnos probar partes de la lógica fuera del entorno 
de Alexa o Lambda. A nivel de diseño funciona como un entry point alternativo 
que mantuvimos separado del handler principal para no tener que modificar el 
código de producción solo para realizar pruebas rápidas.

Aunque este archivo no participa en el flujo real de la skill cuando ya está en 
producción nos fue de gran utilidad durante la etapa de desarrollo ya que nos 
permitió validar la lógica de generación de rutinas de manera ágil sin la 
necesidad de estar desplegando en AWS en cada intento.

---

### **routines.json**

En este archivo guardamos toda la base de datos de los ejercicios en formato 
JSON incluyendo desde los calentamientos y los sets principales para cada 
combinación de nivel o tipo hasta la vuelta a la calma. Aquí la decisión de 
diseño más importante fue separar completamente los datos de la lógica evitando 
hardcodear nombres o textos en el código de Python y manejándolos mejor como 
una configuración externa.

Dentro del flujo la aplicación carga este archivo al inicio y luego nuestros 
módulos de selección y creación lo utilizan para armar la rutina de modo que si 
necesitamos añadir o modificar ejercicios en el futuro lo hacemos editando 
directamente este JSON sin tocar la programación.

---

### **requirements.txt**

En este archivo listamos todas las dependencias externas del proyecto como el 
ask-sdk y boto3 siguiendo la práctica estándar de Python de tener todo 
centralizado para facilitar la instalación. Aunque no participa activamente en 
la lógica de la conversación es un componente clave para el despliegue ya que 
sin estas librerías la Lambda no tendría las herramientas necesarias para usar 
el SDK de Alexa ni para conectarse a nuestros servicios en la nube.
