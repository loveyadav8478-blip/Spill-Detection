# FRONTEND TECHNOLOGY
HTML,CSS,JS
REACT
BOOTSTRAP
MATERIAL UI


# BACKEND TECHNOLOGY
NODE.JS
EXPRESS.JS


# DATABASE 
MOBNGO_DB

# TESTING FRAMEWORK

JEST

# DEPLOYMENT 

AWS

-------------------------------------------------------------------------------------------------

# create react app-
npx create-react-app frontend

# to start react app
npm start

# FRONTEND
    public
        |
        |_ index.html
        |_manifest.json
        |_robots.txt
    src
      |_index.html
      |_index.js

# to get all dependency command- [node modules]
npm i

-------------------------------------------------------------------------------------------------

# create a [landing_page] folder in src folder-
    src
     |_landing_page
            |_home -(component + rapper_page)
            |_signup
            |_about
            |_pricing
            |_product
            |_support


-------------------------------------------------------------------------------------------------

# add bootstrap [file & Font Awesome link] in public/index.html file-
    public
        |_index.html

------------------------------------------------------------------------------------------------        

# add all (assist) in [media] folder in public folder-
    public
        |_index.html
        |_ media (all required assist)

<!-- react command -->
    install an extention called - [Simple React Snippets] in vscode
    for basic set up
   - [imr]
   - [ffc] 

-------------------------------------------------------------------------------------------------

## for routing install package
npm i react-router-dom

# set up route in
src
  |_index.js


- import {BrowserRouter,Routes,Route} from 'react-router-dom';
- import Homepage from './landing_page/1.home/Homepage';

<BrowserRouter>
    <Routes>
        <route path="/" element={<homepage.js/>}><route/>
    <Routes/>
<BrowserRouter/>

-------------------------------------------------------------------------------------------------

# dashboard
to create a route in right half we use react hook


src
  |_components
        |_Menu.js



import {Link} from "react-router-dom";
import {useState} from "react;

const [rightfxn, Setrightfxn]=useState(0);
const handleMenuclickfxn (index){
    Setrightfxn(index);
}


<Link to="/" onClick={()=> handleMenuclickfxn(0)}><Link/>

<Link to="/orders" onClick={()=> handleMenuclickfxn(1)} ></Link>













------------------------------------------------------------------------------------------------------------------
backend-

npm i nodemon                             [to restart server with every line of code]
npm i express                             [to connect with server]

    -npm i body-parser                         [to transfer data through api]  
-   -npm i cors                               - gi[cross origin resource sharing] as [ to stablish communication btw dashboard & frontend & backend is on diff url]

npm i dotenv 
npm i mongoose                            [to connect with database]
npm i passport 
npm i passport-local-mongoose


npm init                                  [to make package.json file!]




npm axios                                 [to connect to api]


- body-parser cors are used for fetching data form database to frontend